import logging
import os
import sys
import traceback

from flask import Blueprint

from api._response import ok, fail
from config import USE_REAL_DATA
from services.hive_client import query
from services.queries import (
    kpi_cards_sql, F_DT, F_DAU, F_TOTAL_ORDERS, F_BUY_CONVERSION, F_AVG_PV,
)

bp = Blueprint("kpi", __name__, url_prefix="/api/kpi")
logger = logging.getLogger(__name__)

# 惰性导入 ai/insights（失败不影响 KPI 返回）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_generate_insights = None


def _lazy_insights():
    global _generate_insights
    if _generate_insights is None:
        try:
            from ai.insights import generate_insights as gi
            _generate_insights = gi
        except Exception:
            logger.debug("ai.insights 不可用（缺少 LLM 或依赖），跳过 AI 分析")


def _try_add_insight(data: dict) -> None:
    """尝试为 KPI 数据附加 AI 分析文本。失败静默跳过。"""
    _lazy_insights()
    if _generate_insights is None:
        return
    try:
        kpi_for_insights = {
            "dau": data.get("dau"),
            "dau_change": data.get("dau_change"),
            "total_orders": data.get("orders"),
            "orders_change": data.get("orders_change"),
            "buy_conversion": data.get("conversion_rate"),
            "conversion_change": data.get("conversion_change"),
            "avg_pv": data.get("avg_pv"),
            "avg_pv_change": data.get("avg_pv_change"),
        }
        insight_text = _generate_insights(kpi_for_insights)
        if insight_text:
            data["ai_insight"] = insight_text
    except Exception:
        logger.debug("AI 洞察生成失败（无 LLM key 或网络），跳过: %s", traceback.format_exc())


@bp.route("/cards")
def cards():
    if USE_REAL_DATA:
        try:
            rows = query(kpi_cards_sql()).to_dict("records")
            if not rows:
                return fail("no data", 404)
            today = rows[0]
            prev = rows[1] if len(rows) > 1 else None

            dau = int(today[F_DAU])
            dau_change = (
                (today[F_DAU] - prev[F_DAU]) / prev[F_DAU]
                if prev and prev[F_DAU] else 0.0
            )
            data = {
                "date": str(today.get(F_DT, "2014-12-18")),
                "dau": dau,
                "dau_change": round(float(dau_change), 4),
                "orders": int(today[F_TOTAL_ORDERS]),
                "conversion_rate": round(float(today[F_BUY_CONVERSION]), 4),
                "avg_pv": round(float(today[F_AVG_PV]), 2),
            }
            _try_add_insight(data)
            return ok(data)
        except Exception as e:
            return fail(str(e))

    # Mock：字段对齐 D 前端 api.js mockData.kpi
    data = {
        "date": "2014-12-18",
        "dau": 12345,
        "dau_change": -0.03,
        "orders": 8900,
        "orders_change": 0.061,
        "conversion_rate": 0.0382,
        "conversion_change": 0.005,
        "avg_pv": 8.5,
        "avg_pv_change": 0.024,
    }
    _try_add_insight(data)
    return ok(data)
