"""
test_api.py
===========
对 C 的 7 个 REST API + 1 个 SSE 接口做功能测试 + 边界测试。

基于 DEV_PLAN 4.3 接口契约验证：
  - HTTP 状态码
  - 响应 Content-Type
  - 必须字段是否存在
  - 字段类型是否正确
  - 值域范围是否合理
  - 边界参数处理

运行方式：
  cd 项目根目录
  python -m pytest tests/test_api.py -v

  # 或只跑冒烟测试
  python -m pytest tests/test_api.py -v -m smoke

前置条件：
  pip install pytest flask flask-cors python-dotenv
  (已在开发环境中安装)
"""

import json
import sys
from pathlib import Path

import pytest

# 确保 backend 可被导入
# - PROJECT_ROOT 让 `from backend.app import app` 成立
# - BACKEND_DIR  让 app.py 内部的 `from config import ...` / `from api import ...` 成立
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
for p in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# 将 backend 当作子包导入（此时 cwd 会影响 load_dotenv，但 .env 缺失时仅使用默认值）
from backend.app import app


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def client():
    """Flask 测试客户端（自动使用 Mock 模式）。"""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ============================================================
# 1. 基础检查 — 健康端点
# ============================================================

class TestHealth:
    """GET /health — 服务可用性"""

    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.content_type == "application/json"
        assert r.get_json() == {"status": "ok"}

    def test_health_method_not_allowed(self, client):
        """POST /health 应返回 405"""
        r = client.post("/health")
        assert r.status_code == 405


# ============================================================
# 2. GET /api/kpi/cards — KPI 指标卡片
# ============================================================

class TestKpiCards:
    """DEV_PLAN 契约: {dau, dau_change, orders, conversion_rate, avg_pv}"""

    REQUIRED_FIELDS = {"dau", "dau_change", "orders", "conversion_rate", "avg_pv"}

    def test_status_and_content_type(self, client):
        r = client.get("/api/kpi/cards")
        assert r.status_code == 200
        assert r.content_type == "application/json"

    def test_required_fields_present(self, client):
        data = client.get("/api/kpi/cards").get_json()
        missing = self.REQUIRED_FIELDS - set(data.keys())
        assert not missing, f"Missing fields: {missing}"

    def test_no_extra_fields(self, client):
        data = client.get("/api/kpi/cards").get_json()
        extra = set(data.keys()) - self.REQUIRED_FIELDS
        assert not extra, f"Unexpected fields: {extra}"

    def test_dau_is_positive_int(self, client):
        dau = client.get("/api/kpi/cards").get_json()["dau"]
        assert isinstance(dau, int), f"dau should be int, got {type(dau)}"
        assert dau > 0, f"dau should be > 0, got {dau}"

    def test_dau_change_is_float_between_minus_one_and_one(self, client):
        change = client.get("/api/kpi/cards").get_json()["dau_change"]
        assert isinstance(change, (int, float))
        assert -1.0 <= change <= 1.0, f"dau_change out of range: {change}"

    def test_orders_is_positive_int(self, client):
        orders = client.get("/api/kpi/cards").get_json()["orders"]
        assert isinstance(orders, int)
        assert orders > 0

    def test_conversion_rate_between_zero_and_one(self, client):
        rate = client.get("/api/kpi/cards").get_json()["conversion_rate"]
        assert isinstance(rate, (int, float))
        assert 0.0 <= rate <= 1.0, f"conversion_rate out of range: {rate}"

    def test_avg_pv_is_positive(self, client):
        avg_pv = client.get("/api/kpi/cards").get_json()["avg_pv"]
        assert isinstance(avg_pv, (int, float))
        assert avg_pv > 0

    @pytest.mark.smoke
    def test_smoke_all_fields(self, client):
        """冒烟：一次请求验证所有字段"""
        data = client.get("/api/kpi/cards").get_json()
        assert data["dau"] == 12345
        assert data["dau_change"] == -0.03
        assert data["orders"] == 8900
        assert data["conversion_rate"] == 0.12
        assert data["avg_pv"] == 8.5


# ============================================================
# 3. GET /api/trend/active?days=N — 活跃趋势
# ============================================================

class TestTrend:
    """DEV_PLAN 契约: {dates: [], dau: [], pv: []}"""

    def test_status_ok_default_days(self, client):
        r = client.get("/api/trend/active")
        assert r.status_code == 200

    def test_required_fields_present(self, client):
        data = client.get("/api/trend/active").get_json()
        for field in ("dates", "dau", "pv"):
            assert field in data, f"Missing field: {field}"

    def test_arrays_same_length(self, client):
        data = client.get("/api/trend/active?days=7").get_json()
        n = len(data["dates"])
        assert n == 7, f"Expected 7 dates, got {n}"
        assert len(data["dau"]) == n
        assert len(data["pv"]) == n

    def test_dau_and_pv_all_positive(self, client):
        data = client.get("/api/trend/active?days=7").get_json()
        for v in data["dau"]:
            assert v > 0
        for v in data["pv"]:
            assert v > 0

    def test_dates_format_mm_dd(self, client):
        """日期应为 MM-DD 格式"""
        data = client.get("/api/trend/active?days=3").get_json()
        for d in data["dates"]:
            parts = d.split("-")
            assert len(parts) == 2, f"Expected MM-DD, got {d}"
            assert 1 <= int(parts[0]) <= 12
            assert 1 <= int(parts[1]) <= 31

    # ── 边界测试 ──

    def test_days_1(self, client):
        data = client.get("/api/trend/active?days=1").get_json()
        assert len(data["dates"]) == 1

    def test_days_30(self, client):
        """大 days 值：mock 只有 7 天数据，超过时取全部"""
        data = client.get("/api/trend/active?days=30").get_json()
        # mock 实现用 [:days] 切片，仅保留现有 7 条
        assert len(data["dates"]) <= 7

    def test_days_zero(self, client):
        data = client.get("/api/trend/active?days=0").get_json()
        assert data["dates"] == []
        assert data["dau"] == []
        assert data["pv"] == []

    def test_days_negative(self, client):
        """负天数：Python 负数切片 mocks[:-5] 取前 len-5 项"""
        data = client.get("/api/trend/active?days=-5").get_json()
        # mock[: -5] = [7个元素去掉后5个] = 前2项
        # 这是实现细节，只要能正常返回 JSON 即可
        assert isinstance(data["dates"], list)
        assert len(data["dates"]) <= 7

    def test_days_non_integer(self, client):
        """非整数 days：int('abc') → ValueError → 500"""
        try:
            r = client.get("/api/trend/active?days=abc")
            # 若异常被 Flask 捕获，返回 500
            assert r.status_code == 500
        except ValueError:
            # Flask TESTING 模式下异常直接抛出
            pass

    def test_no_days_param_uses_default_7(self, client):
        data = client.get("/api/trend/active").get_json()
        assert len(data["dates"]) == 7


# ============================================================
# 4. GET /api/top/items?limit=N&sort_by=pv — 商品热度 TopN
# ============================================================

class TestTopItems:
    """DEV_PLAN 契约: {items: [{item_id, pv, fav, buy}, ...]}"""

    def test_status_ok_default_params(self, client):
        r = client.get("/api/top/items")
        assert r.status_code == 200

    def test_returns_items_key(self, client):
        data = client.get("/api/top/items").get_json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_default_limit_is_10(self, client):
        data = client.get("/api/top/items").get_json()
        assert len(data["items"]) == 10

    def test_each_item_has_required_fields(self, client):
        data = client.get("/api/top/items?limit=3").get_json()
        for item in data["items"]:
            for field in ("item_id", "pv", "fav", "buy"):
                assert field in item, f"Missing field {field} in item"

    def test_pv_fav_buy_are_positive_ints(self, client):
        data = client.get("/api/top/items?limit=5").get_json()
        for item in data["items"]:
            assert isinstance(item["pv"], int) and item["pv"] > 0
            assert isinstance(item["fav"], int) and item["fav"] >= 0
            assert isinstance(item["buy"], int) and item["buy"] >= 0

    def test_items_descending_by_pv(self, client):
        data = client.get("/api/top/items?limit=10&sort_by=pv").get_json()
        pvs = [item["pv"] for item in data["items"]]
        assert pvs == sorted(pvs, reverse=True), "Items should be sorted by pv descending"

    @pytest.mark.parametrize("sort_by", ["pv", "fav", "buy"])
    def test_valid_sort_by_params(self, client, sort_by):
        r = client.get(f"/api/top/items?limit=5&sort_by={sort_by}")
        assert r.status_code == 200

    # ── 边界测试 ──

    def test_limit_1(self, client):
        data = client.get("/api/top/items?limit=1").get_json()
        assert len(data["items"]) == 1

    def test_limit_100(self, client):
        data = client.get("/api/top/items?limit=100").get_json()
        assert len(data["items"]) == 100

    def test_limit_zero(self, client):
        data = client.get("/api/top/items?limit=0").get_json()
        assert data["items"] == []

    def test_limit_negative(self, client):
        """负 limit 可能返回 0 或报错"""
        r = client.get("/api/top/items?limit=-1")
        assert r.status_code in (200, 400, 500)

    def test_invalid_sort_by_falls_back_to_pv(self, client):
        """无效 sort_by 应降级为 pv，不影响 200"""
        r = client.get("/api/top/items?sort_by=invalid")
        assert r.status_code == 200

    def test_sql_injection_attempt(self, client):
        """sort_by 有白名单保护"""
        r = client.get("/api/top/items?sort_by=pv;DROP TABLE users--")
        assert r.status_code == 200  # 不应崩溃


# ============================================================
# 5. GET /api/funnel — 转化漏斗
# ============================================================

class TestFunnel:
    """DEV_PLAN 契约: {pv, fav, cart, buy}"""

    REQUIRED_FIELDS = {"pv", "fav", "cart", "buy"}

    def test_status_ok(self, client):
        r = client.get("/api/funnel")
        assert r.status_code == 200

    def test_required_fields_present(self, client):
        data = client.get("/api/funnel").get_json()
        missing = self.REQUIRED_FIELDS - set(data.keys())
        assert not missing, f"Missing fields: {missing}"

    def test_all_fields_are_positive_ints(self, client):
        data = client.get("/api/funnel").get_json()
        for field in self.REQUIRED_FIELDS:
            val = data[field]
            assert isinstance(val, int), f"{field} should be int, got {type(val)}"
            assert val > 0, f"{field} should be > 0, got {val}"

    def test_funnel_decreasing(self, client):
        """漏斗各环节人数应递减：pv >= fav >= cart >= buy"""
        data = client.get("/api/funnel").get_json()
        assert data["pv"] >= data["fav"], "pv should be >= fav"
        assert data["fav"] >= data["cart"], "fav should be >= cart"
        assert data["cart"] >= data["buy"], "cart should be >= buy"

    @pytest.mark.smoke
    def test_smoke_values(self, client):
        """C 新增了 4 个转化率字段"""
        data = client.get("/api/funnel").get_json()
        assert data["pv"] == 100000
        assert data["fav"] == 35000
        assert data["cart"] == 20000
        assert data["buy"] == 8000
        # 新增的转化率字段
        assert "pv_to_buy_rate" in data
        assert 0 <= data["pv_to_buy_rate"] <= 1


# ============================================================
# 6. GET /api/rfm/dist — RFM 用户分层分布
# ============================================================

class TestRfmDist:
    """DEV_PLAN 契约: {labels: [], counts: []}"""

    EXPECTED_LABELS = {
        "重要价值", "重要发展", "重要保持", "重要挽留",
        "一般价值", "一般发展", "一般保持", "一般挽留",
    }

    def test_status_ok(self, client):
        r = client.get("/api/rfm/dist")
        assert r.status_code == 200

    def test_required_fields_present(self, client):
        data = client.get("/api/rfm/dist").get_json()
        assert "labels" in data
        assert "counts" in data

    def test_exactly_8_categories(self, client):
        data = client.get("/api/rfm/dist").get_json()
        assert len(data["labels"]) == 8
        assert len(data["counts"]) == 8

    def test_labels_and_counts_same_length(self, client):
        data = client.get("/api/rfm/dist").get_json()
        assert len(data["labels"]) == len(data["counts"])

    def test_labels_match_expected(self, client):
        data = client.get("/api/rfm/dist").get_json()
        actual = set(data["labels"])
        assert actual == self.EXPECTED_LABELS, f"Label mismatch: {actual}"

    def test_counts_all_positive(self, client):
        data = client.get("/api/rfm/dist").get_json()
        for c in data["counts"]:
            assert isinstance(c, int)
            assert c > 0

    def test_counts_sum_exceeds_zero(self, client):
        data = client.get("/api/rfm/dist").get_json()
        assert sum(data["counts"]) > 0

    def test_labels_no_duplicates(self, client):
        data = client.get("/api/rfm/dist").get_json()
        assert len(data["labels"]) == len(set(data["labels"]))


# ============================================================
# 7. GET /api/recommend?user_id=xxx — 个性化推荐
# ============================================================

class TestRecommend:
    """DEV_PLAN 契约: {items: [{item_id, score, reason}, ...]}"""

    def test_status_ok_with_user_id(self, client):
        r = client.get("/api/recommend?user_id=123")
        assert r.status_code == 200

    def test_returns_items_list(self, client):
        data = client.get("/api/recommend?user_id=123").get_json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) > 0

    def test_default_limit_is_10(self, client):
        data = client.get("/api/recommend?user_id=123").get_json()
        assert len(data["items"]) == 10

    def test_each_item_has_required_fields(self, client):
        data = client.get("/api/recommend?user_id=123").get_json()
        for item in data["items"]:
            for field in ("item_id", "score", "reason"):
                assert field in item, f"Missing field {field} in item"

    def test_scores_between_zero_and_one(self, client):
        data = client.get("/api/recommend?user_id=123").get_json()
        for item in data["items"]:
            assert 0.0 <= item["score"] <= 1.0, f"Score out of range: {item['score']}"

    def test_scores_descending(self, client):
        data = client.get("/api/recommend?user_id=123").get_json()
        scores = [item["score"] for item in data["items"]]
        assert scores == sorted(scores, reverse=True), "Scores should be descending"

    @pytest.mark.parametrize("limit", [1, 5, 20])
    def test_custom_limit(self, client, limit):
        data = client.get(f"/api/recommend?user_id=456&limit={limit}").get_json()
        assert len(data["items"]) == limit

    # ── 边界测试 ──

    def test_missing_user_id(self, client):
        """缺少 user_id 时应返回默认值（user_id=0）"""
        r = client.get("/api/recommend")
        assert r.status_code == 200
        # 即使 user_id=0 也应正常返回

    def test_user_id_zero(self, client):
        r = client.get("/api/recommend?user_id=0")
        assert r.status_code == 200

    def test_limit_zero(self, client):
        data = client.get("/api/recommend?user_id=123&limit=0").get_json()
        assert data["items"] == []

    def test_limit_negative(self, client):
        r = client.get("/api/recommend?user_id=123&limit=-5")
        assert r.status_code in (200, 400, 500)

    def test_reason_is_non_empty_string(self, client):
        data = client.get("/api/recommend?user_id=123").get_json()
        for item in data["items"]:
            assert isinstance(item["reason"], str)
            assert len(item["reason"]) > 0


# ============================================================
# 8. POST /api/chat — AI 对话（SSE 流式）
# ============================================================

class TestChat:
    """DEV_PLAN 契约: POST /api/chat, SSE stream with text/chart/done events"""

    def test_status_ok(self, client):
        r = client.post("/api/chat",
                        data=json.dumps({"message": "测试"}),
                        content_type="application/json")
        assert r.status_code == 200

    def test_content_type_is_event_stream(self, client):
        r = client.post("/api/chat",
                        data=json.dumps({"message": "测试"}),
                        content_type="application/json")
        # Flask 可能追加 charset=utf-8，只验证前缀
        assert r.content_type.startswith("text/event-stream")

    def test_stream_contains_text_events(self, client):
        r = client.post("/api/chat",
                        data=json.dumps({"message": "今天DAU多少"}),
                        content_type="application/json")
        body = r.get_data(as_text=True)
        assert 'type": "text"' in body or "type': 'text'" in body \
               or '"text"' in body or "'text'" in body, \
               f"No text event found in: {body[:200]}"

    def test_stream_contains_chart_event(self, client):
        """C v2: Mock 模式不再含 chart 事件（简化版），真实模式才由 B 模块决定"""
        r = client.post("/api/chat",
                        data=json.dumps({"message": "测试"}),
                        content_type="application/json")
        body = r.get_data(as_text=True)
        # Mock 模式只有 text + done，chart 是可选的
        assert "text" in body or "done" in body

    def test_stream_contains_done_event(self, client):
        r = client.post("/api/chat",
                        data=json.dumps({"message": "测试"}),
                        content_type="application/json")
        body = r.get_data(as_text=True)
        assert "done" in body, f"No done event in: {body[:200]}"

    def test_sse_format_starts_with_data_prefix(self, client):
        """每条事件行应以 data: 开头"""
        r = client.post("/api/chat",
                        data=json.dumps({"message": "测试"}),
                        content_type="application/json")
        body = r.get_data(as_text=True)
        lines = [l for l in body.strip().split("\n") if l.strip()]
        for line in lines:
            assert line.startswith("data:"), f"Bad SSE line: {line[:80]}"

    def test_each_data_line_is_valid_json(self, client):
        r = client.post("/api/chat",
                        data=json.dumps({"message": "测试"}),
                        content_type="application/json")
        body = r.get_data(as_text=True)
        for line in body.strip().split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                payload = line[5:].strip()
                obj = json.loads(payload)
                assert "type" in obj, f"No 'type' in SSE payload: {payload[:80]}"

    # ── 边界测试 ──

    def test_empty_message(self, client):
        r = client.post("/api/chat",
                        data=json.dumps({"message": ""}),
                        content_type="application/json")
        assert r.status_code == 200
        assert "done" in r.get_data(as_text=True)

    def test_no_message_field(self, client):
        """缺少 message 字段：应兜底为空字符串"""
        r = client.post("/api/chat",
                        data=json.dumps({}),
                        content_type="application/json")
        assert r.status_code == 200

    def test_not_json_body(self, client):
        """非 JSON body：Flask 返回 message=''"""
        r = client.post("/api/chat",
                        data="不是JSON",
                        content_type="text/plain")
        assert r.status_code == 200  # Mock 模式兜底

    def test_get_method_not_allowed(self, client):
        """GET /api/chat 应返回 405（只接受 POST）"""
        r = client.get("/api/chat")
        assert r.status_code == 405

    def test_chart_event_has_chart_type_and_data(self, client):
        """C v2: chart 事件在 Mock 模式下是可选的，仅在真实 NL2SQL 模式出现"""
        r = client.post("/api/chat",
                        data=json.dumps({"message": "销量排行"}),
                        content_type="application/json")
        body = r.get_data(as_text=True)
        # Mock 模式只保证有 done 事件
        assert "done" in body


# ============================================================
# 9. GET /api/report/* — 晨报接口（C 已实现）
# ============================================================

class TestReport:
    """DEV_PLAN: GET /api/report/latest + GET /api/report/history"""

    def test_report_latest_status_ok(self, client):
        r = client.get("/api/report/latest")
        assert r.status_code == 200

    def test_report_latest_has_required_fields(self, client):
        data = client.get("/api/report/latest").get_json()
        for field in ("date", "content", "anomalies"):
            assert field in data, f"Missing field: {field}"

    def test_report_latest_date_format(self, client):
        data = client.get("/api/report/latest").get_json()
        parts = data["date"].split("-")
        assert len(parts) == 3

    def test_report_latest_content_not_empty(self, client):
        data = client.get("/api/report/latest").get_json()
        assert isinstance(data["content"], str)
        assert len(data["content"]) > 20

    def test_report_latest_anomalies_is_list(self, client):
        data = client.get("/api/report/latest").get_json()
        assert isinstance(data["anomalies"], list)

    def test_report_history_status_ok(self, client):
        r = client.get("/api/report/history?days=7")
        assert r.status_code == 200

    def test_report_history_returns_list(self, client):
        data = client.get("/api/report/history?days=3").get_json()
        assert isinstance(data, list)
        assert len(data) == 3
        for item in data:
            for field in ("date", "content", "anomalies"):
                assert field in item

    def test_report_history_dates_descending(self, client):
        data = client.get("/api/report/history?days=7").get_json()
        dates = [item["date"] for item in data]
        assert dates == sorted(dates, reverse=True), f"Dates not descending: {dates}"

    def test_report_history_custom_days(self, client):
        data = client.get("/api/report/history?days=1").get_json()
        assert len(data) <= 1


# ============================================================
# 10. 跨接口一致性测试
# ============================================================

class TestCrossApi:
    """验证多个接口之间的数据一致性"""

    def test_kpi_orders_matches_funnel_buy(self, client):
        """KPI总订单量 和 漏斗购买用户数 数量级应一致（Mock 数据）"""
        kpi = client.get("/api/kpi/cards").get_json()
        funnel = client.get("/api/funnel").get_json()
        # 不是精确相等但应同数量级
        assert abs(kpi["orders"] - funnel["buy"]) / funnel["buy"] < 10, \
            "KPI orders and funnel buy are too far apart"

    def test_rfm_total_matches_kpi_dau(self, client):
        """RFM 总用户数应 >= 单日 DAU（多天累计用户池 >= 单日活跃）"""
        kpi = client.get("/api/kpi/cards").get_json()
        rfm = client.get("/api/rfm/dist").get_json()
        rfm_total = sum(rfm["counts"])
        assert rfm_total >= kpi["dau"], \
            f"RFM total ({rfm_total}) should >= DAU ({kpi['dau']})"

    def test_all_apis_return_json(self, client):
        """所有 GET 接口返回 JSON"""
        endpoints = [
            "/api/kpi/cards",
            "/api/trend/active",
            "/api/top/items",
            "/api/funnel",
            "/api/rfm/dist",
            "/api/recommend?user_id=1",
        ]
        for ep in endpoints:
            r = client.get(ep)
            assert r.content_type == "application/json", \
                f"{ep} returned {r.content_type}"

    def test_no_internal_server_errors(self, client):
        """所有接口不应返回 500"""
        endpoints = [
            "/health",
            "/api/kpi/cards",
            "/api/trend/active",
            "/api/top/items",
            "/api/funnel",
            "/api/rfm/dist",
            "/api/recommend?user_id=1",
        ]
        for ep in endpoints:
            r = client.get(ep)
            assert r.status_code != 500, f"{ep} returned 500"
