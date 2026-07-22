"""GET /api/recommend?user_id=xxx —— 用户推荐列表。

推荐路径（优先级从高到低）：
1. 优先查 Hive ads_user_recommend（B 的 Item-CF 结果，按 score 降序取 TopN）
2. 表空或不存在 → 自动降级 dws_item_day 全站热销兜底
3. Hive 全挂 → Mock

返回格式不变，字段：item_id, name, score, reason
"""
from flask import Blueprint, request

from api._response import ok, fail
from config import USE_REAL_DATA

bp = Blueprint("recommend", __name__, url_prefix="/api/recommend")


def _query_top_n(user_id: int, limit: int) -> list[dict]:
    """从 ads_user_recommend 按 score 降序取 TopN。"""
    from services.hive_client import query

    sql = """
        SELECT user_id, item_id, score, reason
        FROM ads_user_recommend
        WHERE user_id = %(uid)s
        ORDER BY score DESC
        LIMIT %(lim)s
    """
    params = {"uid": user_id, "lim": limit}
    df = query(sql % params)
    return [
        {"item_id": str(r["item_id"]), "name": f"商品 {r['item_id']}",
         "score": round(float(r["score"]), 4), "reason": str(r.get("reason") or "协同过滤")}
        for _, r in df.iterrows()
    ]


def _query_hot_fallback(user_id: int, limit: int) -> list[dict]:
    """全站热销兜底：dws_item_day 近 30 天按 buy_cnt 降序。"""
    from services.hive_client import query

    sql = """
        SELECT item_id, SUM(buy_cnt) AS total_buy, SUM(pv_cnt) AS total_pv
        FROM dws_item_day
        WHERE dt BETWEEN '2014-11-18' AND '2014-12-18'
        GROUP BY item_id
        ORDER BY total_buy DESC
        LIMIT %(lim)s
    """
    params = {"lim": limit}
    df = query(sql % params)
    return [
        {"item_id": str(r["item_id"]), "name": f"商品 {r['item_id']}",
         "score": round(float(r["total_buy"]) / max(float(df.iloc[0]["total_buy"]), 1), 4),
         "reason": "全站热销"}
        for _, r in df.iterrows()
    ]


def _mock_items(user_id: int, limit: int) -> list[dict]:
    return [
        {
            "item_id": str(232431562 + i * 10000000),
            "name": f"商品 {232431562 + i * 10000000}",
            "score": round(0.95 * (1 - (i - 1) / max(limit, 1)), 2),
            "reason": "协同过滤 + 兴趣相似度",
        }
        for i in range(1, limit + 1)
    ]


@bp.route("")
def recommend():
    user_id = request.args.get("user_id", 0, type=int)
    limit = request.args.get("limit", 10, type=int)

    if not USE_REAL_DATA:
        return ok({"user_id": user_id, "items": _mock_items(user_id, limit)})

    # 路径 1：ads_user_recommend
    try:
        items = _query_top_n(user_id, limit)
        if items:
            return ok({"user_id": user_id, "items": items})
    except Exception as e:
        # 表不存在或其他 Hive 错误，继续降级
        pass

    # 路径 2：全站热销兜底
    try:
        items = _query_hot_fallback(user_id, limit)
        if items:
            return ok({"user_id": user_id, "items": items})
    except Exception as e:
        pass

    # 路径 3：Mock
    return ok({"user_id": user_id, "items": _mock_items(user_id, limit)})

