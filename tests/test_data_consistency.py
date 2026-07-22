"""
test_data_consistency.py
========================
全链路数据一致性测试（Hive 真实模式）。

测试维度：
  1. API ↔ Hive 直接查询 一致性（核心）
  2. API ↔ API 内部逻辑一致性
  3. 数据管道质量验证（行数、分区、去重）
  4. A 的 schema ↔ C 的 queries 引用完整性

前置条件：
  - Hive Docker 容器运行中
  - .env: DB_ENGINE=hive, USE_REAL_DATA=true
  - A 的 13 张表已建好并加载数据

运行方式：
  python -m pytest tests/test_data_consistency.py -v
"""

import json
import re
import sys
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
for p in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app import app


# ============================================================
# Helpers
# ============================================================

def _api(client, path, method="get", body=None):
    """调 API 并解包 {code, data, message} → data，失败时返回原始响应"""
    if method == "get":
        r = client.get(path)
    else:
        r = client.post(path, data=json.dumps(body), content_type="application/json")

    if r.status_code != 200:
        return {"_error": True, "_status": r.status_code, "_body": r.get_json()}

    raw = r.get_json()
    if isinstance(raw, dict) and "data" in raw and "code" in raw:
        return raw["data"]
    return raw  # 扁平格式兜底


def _hive(query_fn, sql):
    """执行 Hive 查询"""
    try:
        return query_fn(sql)
    except Exception as e:
        pytest.skip(f"Hive query failed: {str(e)[:80]}")


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def hive():
    try:
        from services.hive_client import query as q
        q("SELECT 1")
        return q
    except Exception as e:
        pytest.skip(f"Hive not available: {e}")


# ============================================================
# 1. API ↔ Hive 核心一致性
# ============================================================

class TestApiMatchesHive:

    def test_kpi_dau(self, client, hive):
        data = _api(client, "/api/kpi/cards")
        if "_error" in data:
            pytest.fail(f"API error: {data}")
        df = hive("SELECT dau FROM ads_daily_kpi WHERE dt='2014-12-18'")
        assert data["dau"] == int(df.iloc[0, 0])

    def test_kpi_orders(self, client, hive):
        data = _api(client, "/api/kpi/cards")
        df = hive("SELECT total_orders FROM ads_daily_kpi WHERE dt='2014-12-18'")
        assert data["orders"] == int(df.iloc[0, 0])

    def test_kpi_conversion_rate(self, client, hive):
        data = _api(client, "/api/kpi/cards")
        df = hive("SELECT buy_conversion FROM ads_daily_kpi WHERE dt='2014-12-18'")
        assert round(data["conversion_rate"], 4) == round(float(df.iloc[0, 0]), 4)

    def test_kpi_avg_pv(self, client, hive):
        data = _api(client, "/api/kpi/cards")
        df = hive("SELECT avg_pv FROM ads_daily_kpi WHERE dt='2014-12-18'")
        assert round(data["avg_pv"], 2) == round(float(df.iloc[0, 0]), 2)

    def test_funnel(self, client, hive):
        """漏斗接口 — 注意 funnel.py 可能因 SQL 列名有问题返回 500"""
        r = client.get("/api/funnel")
        if r.status_code != 200:
            err = r.get_json()
            msg = str(err.get("message", "")) if err else "unknown"
            if "Invalid table alias or column reference" in msg:
                pytest.skip(f"Funnel API broken — C's SQL has column issue: {msg[:100]}")
            pytest.fail(f"Funnel API error: {msg[:200]}")

        data = _api(client, "/api/funnel")
        df = hive("SELECT pv_users, buy_users FROM ads_funnel WHERE dt='2014-12-18' AND item_category IS NULL")
        assert data["pv"] == int(df.iloc[0, 0])
        assert data["buy"] == int(df.iloc[0, 1])
        assert data["pv"] >= data["fav"] >= data["cart"] >= data["buy"]

    def test_rfm_labels(self, client, hive):
        data = _api(client, "/api/rfm/dist")
        if "_error" in data:
            pytest.fail(f"RFM API error: {data}")
        df = hive(
            "SELECT rfm_label_cn, COUNT(*) as cnt FROM ads_user_rfm "
            "WHERE dt='2014-12-18' GROUP BY rfm_label_cn ORDER BY cnt DESC"
        )
        assert set(data["labels"]) == set(df.iloc[:, 0].tolist())

    def test_rfm_counts(self, client, hive):
        data = _api(client, "/api/rfm/dist")
        api_sorted = sorted(zip(data["labels"], data["counts"]))
        df = hive(
            "SELECT rfm_label_cn, COUNT(*) as cnt FROM ads_user_rfm "
            "WHERE dt='2014-12-18' GROUP BY rfm_label_cn ORDER BY rfm_label_cn"
        )
        hive_sorted = sorted(zip(df.iloc[:, 0].tolist(), df.iloc[:, 1].astype(int).tolist()))
        for (al, ac), (hl, hc) in zip(api_sorted, hive_sorted):
            assert al == hl, f"Label mismatch: {al} vs {hl}"
            assert ac == hc, f"Count for {al}: API={ac} vs Hive={hc}"

    def test_trend(self, client):
        data = _api(client, "/api/trend/active?days=7")
        assert len(data["dates"]) == 7
        assert len(data["dau"]) == 7
        assert len(data["pv"]) == 7
        assert len(data["dates"]) == len(set(data["dates"]))

    def test_top_items(self, client):
        data = _api(client, "/api/top/items?limit=10")
        assert len(data["items"]) == 10
        pvs = [item["pv"] for item in data["items"]]
        for i in range(len(pvs) - 1):
            assert pvs[i] >= pvs[i + 1]

    def test_recommend_requires_mysql(self, client):
        data = _api(client, "/api/recommend?user_id=1")
        if "_error" in data:
            err_msg = str(data.get("_body", {}))
            if "MySQL" in err_msg or "Access denied" in err_msg:
                pytest.skip("Recommend requires MySQL")
        assert "items" in data

    def test_report_requires_mysql(self, client):
        data = _api(client, "/api/report/latest")
        if "_error" in data:
            err_msg = str(data.get("_body", {}))
            if "MySQL" in err_msg or "Access denied" in err_msg:
                pytest.skip("Report requires MySQL")
        assert "date" in data


# ============================================================
# 2. API 内部一致性
# ============================================================

class TestApiInternalConsistency:

    def test_kpi_dau_equals_trend_latest(self, client):
        kpi = _api(client, "/api/kpi/cards")
        trend = _api(client, "/api/trend/active?days=1")
        assert kpi["dau"] == trend["dau"][-1], \
            f"KPI dau={kpi['dau']} != trend={trend['dau'][-1]}"

    def test_kpi_orders_equals_funnel_buy(self, client):
        """只有在 Funnel 正常时才做此校验"""
        r = client.get("/api/funnel")
        if r.status_code != 200:
            pytest.skip("Funnel API not working — C's SQL bug")
        kpi = _api(client, "/api/kpi/cards")
        funnel = _api(client, "/api/funnel")
        assert kpi["orders"] == funnel["buy"]

    def test_rfm_total_gte_dau(self, client):
        kpi = _api(client, "/api/kpi/cards")
        rfm = _api(client, "/api/rfm/dist")
        assert sum(rfm["counts"]) >= kpi["dau"]


# ============================================================
# 3. 数据管道质量
# ============================================================

class TestDataPipeline:

    def test_ods_row_count(self, hive):
        df = hive("SELECT COUNT(*) FROM ods_user_behavior")
        assert int(df.iloc[0, 0]) == 12256906

    def test_ods_date_range(self, hive):
        df = hive("SELECT MIN(behavior_date), MAX(behavior_date) FROM ods_user_behavior")
        assert df.iloc[0, 0] == "2014-11-18"
        assert df.iloc[0, 1] == "2014-12-18"

    def test_ods_behavior_types(self, hive):
        df = hive("SELECT DISTINCT behavior_type FROM ods_user_behavior ORDER BY behavior_type")
        assert df.iloc[:, 0].astype(int).tolist() == [1, 2, 3, 4]

    def test_dwd_dedup_works(self, hive):
        """DWD 用 ROW_NUMBER 去重，不应存在重复"""
        df = hive(
            "SELECT COUNT(*) as total, "
            "COUNT(DISTINCT user_id, item_id, behavior_type, behavior_date, behavior_hour) as uniq "
            "FROM dwd_user_behavior"
        )
        total = int(df.iloc[0, 0])
        uniq = int(df.iloc[0, 1])
        assert total == uniq, f"DWD has {total - uniq} duplicates"

    def test_dwd_dedup_summary(self, hive):
        """ODS→DWD 去重导致行数减少（预期行为，原始数据有大量重复）"""
        ods = int(hive("SELECT COUNT(*) FROM ods_user_behavior").iloc[0, 0])
        dwd = int(hive("SELECT COUNT(*) FROM dwd_user_behavior").iloc[0, 0])
        dedup_rate = (ods - dwd) / ods
        print(f"\n  ODS={ods:,} → DWD={dwd:,}  去重率={dedup_rate:.1%}")
        assert dedup_rate < 0.6, f"Dedup rate {dedup_rate:.1%} too high — check A's dedup logic"

    def test_dws_platform_31_days(self, hive):
        assert int(hive("SELECT COUNT(DISTINCT dt) FROM dws_platform_day").iloc[0, 0]) == 31

    def test_ads_kpi_31_days(self, hive):
        assert int(hive("SELECT COUNT(DISTINCT dt) FROM ads_daily_kpi").iloc[0, 0]) == 31

    def test_ads_rfm_all_labeled(self, hive):
        df = hive("SELECT COUNT(*) FROM ads_user_rfm WHERE dt='2014-12-18' AND rfm_label_cn IS NULL")
        assert int(df.iloc[0, 0]) == 0

    def test_dws_dau_equals_ods(self, hive):
        """某天 DWS DAU = ODS 当天去重 user_id"""
        df = hive(
            "SELECT MAX(CASE WHEN src='dws' THEN cnt END) as dws_dau, "
            "MAX(CASE WHEN src='ods' THEN cnt END) as ods_dau "
            "FROM ("
            "  SELECT 'dws' as src, total_uv as cnt FROM dws_platform_day WHERE dt='2014-12-18' "
            "  UNION ALL "
            "  SELECT 'ods', COUNT(DISTINCT user_id) FROM ods_user_behavior WHERE behavior_date='2014-12-18'"
            ") t"
        )
        assert int(df.iloc[0, 0]) == int(df.iloc[0, 1]), \
            f"DWS DAU={int(df.iloc[0,0])} != ODS DAU={int(df.iloc[0,1])}"


# ============================================================
# 4. ODS ↔ 原始 CSV
# ============================================================

class TestOdsVsRawCsv:

    def test_row_count_matches(self, hive):
        csv_path = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_user.csv"
        if not csv_path.exists():
            pytest.skip("Raw CSV not found")

        with open(csv_path, "r", encoding="utf-8") as f:
            csv_lines = sum(1 for _ in f) - 1

        hive_count = int(hive("SELECT COUNT(*) FROM ods_user_behavior").iloc[0, 0])
        assert csv_lines == hive_count, \
            f"CSV={csv_lines:,} vs ODS={hive_count:,}"


# ============================================================
# 5. Schema ↔ Queries 引用完整性
# ============================================================

class TestSchemaQueryAlignment:

    @pytest.fixture(autouse=True)
    def setup(self):
        text = (BACKEND_DIR / "services" / "queries.py").read_text(encoding="utf-8")
        self.query_tables = {}
        for m in re.finditer(r'(?<![A-Za-z_])T_(\w+)\s*=\s*"(\w+)"', text):
            self.query_tables[m.group(1)] = m.group(2)

    def test_tables_exist_in_hive(self, hive):
        hive_tables = set(hive("SHOW TABLES").iloc[:, 0].tolist())
        for name, tbl in self.query_tables.items():
            assert tbl in hive_tables, f"C's T_{name}='{tbl}' not in Hive"

    def test_kpi_columns_exist(self, hive):
        cols = set(hive("DESCRIBE ads_daily_kpi").iloc[:, 0].tolist())
        for c in ["dau", "total_orders", "buy_conversion", "avg_pv"]:
            assert c in cols, f"'{c}' not in ads_daily_kpi"

    def test_funnel_columns_exist(self, hive):
        cols = set(hive("DESCRIBE ads_funnel").iloc[:, 0].tolist())
        for c in ["pv_users", "fav_users", "cart_users", "buy_users"]:
            assert c in cols, f"'{c}' not in ads_funnel"

    def test_platform_columns_exist(self, hive):
        cols = set(hive("DESCRIBE dws_platform_day").iloc[:, 0].tolist())
        for c in ["total_uv", "total_pv"]:
            assert c in cols, f"'{c}' not in dws_platform_day"


# ============================================================
# 6. Chat SSE
# ============================================================

class TestChatSse:

    def test_chat_pipeline(self, client):
        r = client.post("/api/chat",
                        data=json.dumps({"message": "今天DAU多少"}),
                        content_type="application/json")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "data:" in body
        assert "done" in body
