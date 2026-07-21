"""GET /api/recommend?user_id=xxx —— 用户推荐列表。

Real 模式：读 MySQL 中 B 的 recommender.py 产出的推荐结果表。
USE_REAL_DATA=false 或不具备连接时返回 Mock。
"""
from flask import Blueprint, request

from api._response import ok, fail
from config import USE_REAL_DATA
from services.db import get_recommend

bp = Blueprint("recommend", __name__, url_prefix="/api/recommend")


@bp.route("")
def recommend():
    user_id = request.args.get("user_id", 0, type=int)
    limit = request.args.get("limit", 10, type=int)

    if USE_REAL_DATA:
        try:
            rows = get_recommend(user_id, limit)
            items = [
                {"item_id": str(r["item_id"]), "name": f"商品 {r['item_id']}",
                 "score": round(float(r["score"]), 4), "reason": r.get("reason", "")}
                for r in rows
            ]
            return ok({"user_id": user_id, "items": items})
        except Exception as e:
            return fail(str(e))

    items = [
        {
            "item_id": str(232431562 + i * 10000000),
            "name": f"商品 {232431562 + i * 10000000}",
            "score": round(0.95 * (1 - (i - 1) / max(limit, 1)), 2),
            "reason": "协同过滤 + 兴趣相似度",
        }
        for i in range(1, limit + 1)
    ]
    return ok({"user_id": user_id, "items": items})
