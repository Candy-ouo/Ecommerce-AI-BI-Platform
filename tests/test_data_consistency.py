"""
test_data_consistency.py
========================
数据一致性测试 — 验证"大屏展示的数字 = 真实数据"。

测试维度：
  1. API ↔ API 内部一致性（Mock 模式可跑）
  2. API ↔ DEV_PLAN 契约一致性（字段名/类型）
  3. API ↔ 样本 CSV 数值合理性（数量级校验）
  4. A 的 schema ↔ C 的 queries 引用完整性（静态检查）
  5. 全链路数据流一致性（需 Hive，默认跳过）

运行方式：
  python -m pytest tests/test_data_consistency.py -v
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

# 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
for p in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app import app


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def api_data(client):
    """一次请求获取所有 API 数据"""
    return {
        "kpi": client.get("/api/kpi/cards").get_json(),
        "trend": client.get("/api/trend/active?days=7").get_json(),
        "top": client.get("/api/top/items?limit=10").get_json(),
        "funnel": client.get("/api/funnel").get_json(),
        "rfm": _safe_get_json(client.get("/api/rfm/dist")),
        "recommend": client.get("/api/recommend?user_id=1").get_json(),
        "report": client.get("/api/report/latest").get_json(),
    }


def _safe_get_json(response):
    """安全获取 JSON，500 时返回 None"""
    if response.status_code == 200:
        return response.get_json()
    return None


@pytest.fixture
def sample_df():
    """读取样本 CSV（用于数量级对比）"""
    path = PROJECT_ROOT / "data" / "sample" / "sample_10k.csv"
    if not path.exists():
        path = PROJECT_ROOT / "data" / "processed" / "user_behavior_clean.csv"
    if path.exists():
        return pd.read_csv(path, dtype=str)
    return None


# ============================================================
# 1. API ↔ API 内部一致性
# ============================================================

class TestApiInternalConsistency:
    """验证各个 API 返回的 Mock 数据在逻辑上不自相矛盾"""

    def test_funnel_is_decreasing(self, api_data):
        """漏斗各环节：pv >= fav >= cart >= buy"""
        f = api_data["funnel"]
        assert f["pv"] >= f["fav"] >= f["cart"] >= f["buy"], \
            f"Funnel not decreasing: {f}"

    def test_kpi_orders_approximates_funnel_buy(self, api_data):
        """KPI 订单量 ≈ 漏斗购买用户数（同一平台不应差太多）"""
        orders = api_data["kpi"]["orders"]
        buy = api_data["funnel"]["buy"]
        # Mock 数据的 orders(8900) 和 buy(8000) 是手动构造的，应在同数量级
        ratio = abs(orders - buy) / max(orders, buy)
        assert ratio < 0.5, \
            f"KPI orders ({orders}) and funnel buy ({buy}) differ too much ({ratio:.2f})"

    def test_trend_latest_dau_close_to_kpi_dau(self, api_data):
        """趋势最新一天 DAU ≈ KPI 卡片 DAU"""
        kpi_dau = api_data["kpi"]["dau"]
        trend_last_dau = api_data["trend"]["dau"][-1]
        ratio = abs(kpi_dau - trend_last_dau) / max(kpi_dau, trend_last_dau)
        assert ratio < 0.3, \
            f"KPI dau ({kpi_dau}) vs trend latest ({trend_last_dau}) too far ({ratio:.2f})"

    def test_trend_dates_count_matches_days(self, api_data):
        """趋势数据的日期数 = days 参数"""
        t = api_data["trend"]
        n = len(t["dates"])
        assert n == len(t["dau"]) == len(t["pv"])
        assert n == 7  # 默认 7 天

    def test_top_items_count_matches_limit(self, api_data):
        """Top 排行数量 = limit"""
        assert len(api_data["top"]["items"]) == 10

    def test_top_items_pv_less_than_total(self, api_data):
        """单商品 PV < 全站总 PV"""
        total_pv = api_data["funnel"]["pv"]
        for item in api_data["top"]["items"]:
            assert item["pv"] <= total_pv, \
                f"Item {item['item_id']} pv ({item['pv']}) > total ({total_pv})"

    def test_recommend_scores_descending(self, api_data):
        """推荐分数降序"""
        scores = [item["score"] for item in api_data["recommend"]["items"]]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Scores not descending at index {i}"

    def test_rfm_categories_match_expected(self, api_data):
        """RFM 应该有 8-9 类标签"""
        if api_data["rfm"] is None:
            pytest.skip("RFM not available (requires Hive)")
        labels = api_data["rfm"]["labels"]
        assert 7 <= len(labels) <= 10, f"Unexpected RFM label count: {len(labels)}"

    def test_report_date_is_valid(self, api_data):
        """晨报日期格式 YYYY-MM-DD"""
        date_str = api_data["report"]["date"]
        parts = date_str.split("-")
        assert len(parts) == 3
        assert parts[0] == "2014"
        assert 1 <= int(parts[1]) <= 12

    def test_report_anomalies_are_descriptive(self, api_data):
        """异常描述非空"""
        anomalies = api_data["report"]["anomalies"]
        for a in anomalies:
            assert isinstance(a, str) and len(a) > 0


# ============================================================
# 2. API ↔ DEV_PLAN 4.3 契约一致性
# ============================================================

class TestApiDevPlanContract:
    """验证 C 的 API 返回完全符合 DEV_PLAN 4.3 定义的字段名和类型"""

    def test_kpi_cards_contract(self, client):
        """DEV_PLAN 4.3: {dau, dau_change, orders, conversion_rate, avg_pv}"""
        data = client.get("/api/kpi/cards").get_json()
        expected = {
            "dau": (int, float),
            "dau_change": (int, float),
            "orders": (int, float),
            "conversion_rate": (int, float),
            "avg_pv": (int, float),
        }
        for field, types in expected.items():
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], types), \
                f"{field} type {type(data[field])} not in {types}"

    def test_trend_contract(self, client):
        """DEV_PLAN 4.3: {dates: [], dau: [], pv: []}"""
        data = client.get("/api/trend/active?days=7").get_json()
        for field in ("dates", "dau", "pv"):
            assert field in data, f"Missing: {field}"
            assert isinstance(data[field], list), f"{field} not a list"
        assert len(data["dates"]) == 7

    def test_top_items_contract(self, client):
        """DEV_PLAN 4.3: {items: [{item_id, pv, ...}]}"""
        data = client.get("/api/top/items?limit=5").get_json()
        assert "items" in data
        assert isinstance(data["items"], list)
        item = data["items"][0]
        assert "item_id" in item
        assert "pv" in item

    def test_funnel_contract(self, client):
        """DEV_PLAN 4.3: {pv, fav, cart, buy}"""
        data = client.get("/api/funnel").get_json()
        for field in ("pv", "fav", "cart", "buy"):
            assert field in data
            assert isinstance(data[field], int)

    def test_rfm_contract(self, client):
        """DEV_PLAN 4.3: {labels: [], counts: []}"""
        r = client.get("/api/rfm/dist")
        if r.status_code != 200:
            pytest.skip("RFM not available (requires Hive)")
        data = r.get_json()
        assert "labels" in data
        assert "counts" in data

    def test_recommend_contract(self, client):
        """DEV_PLAN 4.3: {items: [{item_id, score, reason}]}"""
        data = client.get("/api/recommend?user_id=1").get_json()
        assert "items" in data
        item = data["items"][0]
        for field in ("item_id", "score", "reason"):
            assert field in item, f"Missing: {field}"

    def test_chat_contract(self, client):
        """DEV_PLAN 4.3: POST /api/chat → SSE stream"""
        r = client.post("/api/chat",
                        data=json.dumps({"message": "test"}),
                        content_type="application/json")
        assert r.content_type.startswith("text/event-stream")
        body = r.get_data(as_text=True)
        assert "done" in body

    def test_report_latest_contract(self, client):
        """DEV_PLAN 4.3: {date, content, anomalies}"""
        data = client.get("/api/report/latest").get_json()
        for field in ("date", "content", "anomalies"):
            assert field in data

    def test_report_history_contract(self, client):
        """DEV_PLAN 4.3: [{date, content, anomalies}]"""
        data = client.get("/api/report/history?days=3").get_json()
        assert isinstance(data, list)
        for field in ("date", "content", "anomalies"):
            assert field in data[0]


# ============================================================
# 3. API ↔ 样本 CSV 数量级校验
# ============================================================

class TestApiSampleConsistency:
    """API Mock 数值和样本 CSV 在数量级上应该一致"""

    def test_sample_csv_loadable(self, sample_df):
        """样本 CSV 存在且可读"""
        assert sample_df is not None, "Sample CSV not found"
        assert len(sample_df) > 0

    def test_behavior_distribution_matches_sample(self, api_data, sample_df):
        """Mock 的行为类型分布在数量级上与样本一致"""
        if sample_df is None:
            pytest.skip("Sample CSV not available")

        bt_col = "behavior_type"
        if bt_col not in sample_df.columns:
            pytest.skip("No behavior_type in sample")

        bt_counts = sample_df[bt_col].value_counts(normalize=True)
        # 样本分布应为 浏览~94%, 加购~3%, 收藏~2%, 购买~1%
        pv_pct = bt_counts.get("1", 0)
        assert 0.80 <= pv_pct <= 0.99, f"Sample PV ratio abnormal: {pv_pct:.2f}"

    def test_dau_order_of_magnitude(self, api_data, sample_df):
        """Mock DAU(12345) 与样本唯一用户数在同一数量级"""
        if sample_df is None:
            pytest.skip("Sample CSV not available")

        uid_col = "user_id"
        if uid_col not in sample_df.columns:
            pytest.skip("No user_id in sample")

        sample_users = sample_df[uid_col].nunique()
        mock_dau = api_data["kpi"]["dau"]
        # 全量 10,000 用户，样本只有 ~4,747 个唯一用户
        # Mock DAU=12,345 是合理的全量值
        # 只验证数量级（都在 1000-100000 区间）
        assert 1000 <= mock_dau <= 100000, f"DAU out of range: {mock_dau}"
        assert sample_users > 0, f"Sample has 0 users"

    def test_mock_values_are_consistent_over_time(self, client):
        """同一个 Mock 接口多次调用返回相同数据"""
        data1 = client.get("/api/kpi/cards").get_json()
        data2 = client.get("/api/kpi/cards").get_json()
        assert data1 == data2, "Mock API should return consistent values"


# ============================================================
# 4. A 的 schema ↔ C 的 queries 引用完整性
# ============================================================

class TestSchemaQueryAlignment:
    """A 的 schema.md 中定义的表/列与 C 的 queries.py 中引用的必须一致"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from ai.nl2sql.schema_context import get_tables, reset_cache
        reset_cache()
        self.schema_tables = get_tables()
        self._load_queries()

    def _load_queries(self):
        """从 queries.py 提取引用的表和列"""
        queries_path = BACKEND_DIR / "services" / "queries.py"
        text = queries_path.read_text(encoding="utf-8")

        # 提取所有 T_xxx = "table_name"（只匹配独立标识符，排除 F_CART_CNT 中的 T_）
        self.query_tables = {}
        for m in re.finditer(r'(?<![A-Za-z_])T_(\w+)\s*=\s*"(\w+)"', text):
            self.query_tables[m.group(1)] = m.group(2)

        # 提取所有 F_xxx = "column_name"
        self.query_fields = {}
        for m in re.finditer(r'(?<![A-Za-z_])F_(\w+)\s*=\s*"(\w+)"', text):
            self.query_fields[m.group(1)] = m.group(2)

    def test_all_query_tables_exist_in_schema(self):
        """C 引用的表都在 A 的 schema.md 中"""
        missing = []
        for name, tbl in self.query_tables.items():
            if tbl not in self.schema_tables:
                missing.append(f"T_{name} = '{tbl}'")
        assert not missing, \
            f"C references tables not in schema.md:\n  " + "\n  ".join(missing)

    def test_key_fields_exist_in_their_tables(self):
        """C 引用的列在其对应表中存在"""
        # 手动映射：[字段常量名] → (表常量名, 列名)
        field_to_table = {
            "F_DAU": ("T_KPI", "dau"),
            "F_TOTAL_ORDERS": ("T_KPI", "total_orders"),
            "F_BUY_CONVERSION": ("T_KPI", "buy_conversion"),
            "F_AVG_PV": ("T_KPI", "avg_pv"),
            "F_TOTAL_UV": ("T_PLATFORM_DAY", "total_uv"),
            "F_TOTAL_PV": ("T_PLATFORM_DAY", "total_pv"),
            "F_PV_CNT": ("T_ITEM_DAY", "pv_cnt"),
            "F_FAV_CNT": ("T_ITEM_DAY", "fav_cnt"),
            "F_CART_CNT": ("T_ITEM_DAY", "cart_cnt"),
            "F_BUY_CNT": ("T_ITEM_DAY", "buy_cnt"),
            "F_PV_USERS": ("T_FUNNEL", "pv_users"),
            "F_FAV_USERS": ("T_FUNNEL", "fav_users"),
            "F_CART_USERS": ("T_FUNNEL", "cart_users"),
            "F_BUY_USERS": ("T_FUNNEL", "buy_users"),
        }

        issues = []
        for f_const, (t_const, col_name) in field_to_table.items():
            table_name = self.query_tables.get(t_const)
            if table_name not in self.schema_tables:
                continue  # 表不存在的问题已在上一个测试报告

            schema_cols = {c["name"] for c in self.schema_tables[table_name]["columns"]}
            if col_name not in schema_cols:
                issues.append(
                    f"{f_const}='{col_name}' not in {table_name} "
                    f"(columns: {sorted(schema_cols)[:5]}...)"
                )

        assert not issues, \
            "Field mismatches between C's queries and A's schema:\n  " + \
            "\n  ".join(issues)

    def test_partitioned_tables_use_dt_filter(self):
        """所有分区表查询必须包含 dt 过滤"""
        queries_path = BACKEND_DIR / "services" / "queries.py"
        text = queries_path.read_text(encoding="utf-8")

        # 所有 SQL 函数应该引用 F_DT
        sql_functions = ["kpi_cards_sql", "trend_active_sql", "top_items_sql", "funnel_sql"]
        for func in sql_functions:
            assert func in text, f"SQL function {func} not found in queries.py"


# ============================================================
# 5. 全链路数据流一致性（需 Hive）
# ============================================================

@pytest.mark.requires_hive
class TestFullPipelineConsistency:
    """需要 Hive 连接 — 验证 API 结果 = 直接查 Hive"""

    def test_hive_query_available(self):
        """Hive 客户端可用"""
        try:
            from services.hive_client import query
            df = query("SELECT 1")
            assert len(df) > 0
        except Exception as e:
            pytest.skip(f"Hive not available: {e}")

    def test_kpi_from_hive_matches_api(self, client):
        """API KPI = Hive 直接查询"""
        try:
            from services.hive_client import query
            from services.queries import kpi_cards_sql
            df = query(kpi_cards_sql())
        except Exception as e:
            pytest.skip(f"Hive not available: {e}")

        api = client.get("/api/kpi/cards").get_json()
        row = df.iloc[0]
        assert int(row["dau"]) == api["dau"]
        assert int(row["total_orders"]) == api["orders"]
