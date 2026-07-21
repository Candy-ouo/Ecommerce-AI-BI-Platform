"""
Agent 工具函数

定义 Agent 可调用的工具函数，每个工具通过 HTTP 请求调用 C 的后端 API 获取真实数据。
Agent 通过这组工具自动完成数据分析任务。

工具清单：
    1. get_daily_kpi()           → KPI 指标卡
    2. get_active_trend(days)    → 活跃趋势
    3. get_top_items(limit, by)  → 商品热度排行
    4. get_funnel()              → 转化漏斗
    5. get_rfm_distribution()    → RFM 用户分层

使用方式（被 analysis_agent.py 调用）：
    from ai.agent.tools import TOOLS
    # TOOLS 是 LangChain 兼容的工具列表
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import requests

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

API_BASE = os.getenv("API_BASE", "http://localhost:5000")
TIMEOUT = 10  # 秒


def _get(endpoint: str, params: dict = None) -> dict:
    """统一 GET 请求封装。

    C 的 API 统一返回 {code, message, data}，本函数解包返回 data 层业务数据。
    若 code != 0 或异常，返回 {error: ...}。
    """
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") == 0:
            return body.get("data", {})
        return {"error": body.get("message", f"API returned code={body.get('code')}")}
    except requests.exceptions.ConnectionError:
        logger.warning("Cannot connect to %s (C's backend not running?)", API_BASE)
        return {"error": f"无法连接后端服务 ({API_BASE})"}
    except Exception as e:
        logger.warning("API call failed: %s %s → %s", endpoint, params, e)
        return {"error": str(e)}


# ============================================================
# 工具 1: KPI 指标卡
# ============================================================

def get_daily_kpi() -> dict:
    """
    获取今日核心经营指标。

    Returns:
        {dau, dau_change, orders, orders_change, conversion_rate, conversion_change,
         avg_pv, avg_pv_change, ai_insight?}
        各 _change 为环比变化率（0.03 = +3%）；ai_insight 为 AI 分析文本（仅 LLM 可用时存在）
    """
    return _get("/api/kpi/cards")


# ============================================================
# 工具 2: 活跃趋势
# ============================================================

def get_active_trend(days: int = 7) -> dict:
    """
    获取近 N 天的 DAU/PV 趋势。

    Args:
        days: 天数，默认 7

    Returns:
        {dates: ["12-12",...], dau: [8230,...], pv: [385000,...], orders: [3900,...]}
    """
    return _get("/api/trend/active", {"days": days})


# ============================================================
# 工具 3: 商品/类目热度排行
# ============================================================

def get_top_items(limit: int = 10, sort_by: str = "pv") -> dict:
    """
    获取热度排行 TopN 商品。

    Args:
        limit:  返回数量，默认 10
        sort_by: 排序字段 pv / fav / buy，默认 pv

    Returns:
        {items: [{item_id, pv, fav, buy}, ...]}
    """
    return _get("/api/top/items", {"limit": limit, "sort_by": sort_by})


# ============================================================
# 工具 4: 转化漏斗
# ============================================================

def get_funnel() -> dict:
    """
    获取全站转化漏斗数据（浏览 → 收藏 → 加购 → 购买 各环节人数 + 各级转化率）。

    Returns:
        {pv, fav, cart, buy, pv_to_fav_rate, fav_to_cart_rate, cart_to_buy_rate, pv_to_buy_rate}
    """
    return _get("/api/funnel")


# ============================================================
# 工具 5: RFM 用户分层分布
# ============================================================

def get_rfm_distribution() -> dict:
    """
    获取 RFM 9 类用户分层的人数分布（含"浏览型用户"）。

    Returns:
        {labels: ["重要价值用户",...], counts: [1200,...]}
    """
    return _get("/api/rfm/dist")


# ============================================================
# 工具描述（供 Agent 使用）
# ============================================================

TOOL_DEFINITIONS = [
    {
        "name": "get_daily_kpi",
        "description": "获取今日核心经营指标：DAU、DAU环比变化、订单量、购买转化率、人均PV。用于回答'今天数据怎么样'、'KPI是多少'等整体概览问题。",
        "function": get_daily_kpi,
    },
    {
        "name": "get_active_trend",
        "description": "获取近N天的DAU和PV趋势数据（默认7天）。用于回答'趋势'、'走势'、'最近几天变化'等时序分析问题。参数: days(整数,默认7)。",
        "function": get_active_trend,
    },
    {
        "name": "get_top_items",
        "description": "获取商品热度TopN排行（按浏览量/收藏量/购买量排序）。用于回答'热门商品'、'排行'、'哪些商品最...'等问题。参数: limit(整数,默认10), sort_by(pv/fav/buy,默认pv)。",
        "function": get_top_items,
    },
    {
        "name": "get_funnel",
        "description": "获取全站转化漏斗数据：浏览→收藏→加购→购买各环节用户数。用于回答'转化率'、'漏斗'、'流失'等分析问题。",
        "function": get_funnel,
    },
    {
        "name": "get_rfm_distribution",
        "description": "获取RFM用户价值分层的人数分布（9类标签，含浏览型用户）。用于回答'用户分层'、'高价值用户占比'、'用户结构'等问题。",
        "function": get_rfm_distribution,
    },
]


# ============================================================
# 自检
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    print("Agent Tools - Self Check")
    print(f"  API Base: {API_BASE}")
    print(f"  Tools   : {len(TOOL_DEFINITIONS)}")

    test_funcs = [
        ("KPI", get_daily_kpi),
        ("Trend(3天)", lambda: get_active_trend(3)),
        ("Top5-PV", lambda: get_top_items(5, "pv")),
        ("Funnel", get_funnel),
        ("RFM", get_rfm_distribution),
    ]

    for label, fn in test_funcs:
        result = fn()
        status = "[FAIL]" if "error" in result else "[OK]"
        print(f"\n{status} {label}:")
        print(f"   {json.dumps(result, ensure_ascii=False, indent=2)[:300]}")
