"""GET /api/recommend?user_id=xxx —— 用户推荐列表。

数据来自 MySQL（B 的 recommender.py 产出、A 的 ADS 层写入），
当前返回 Mock，Day 2 后换成 services.db.get_recommend()。
"""
from flask import Blueprint, jsonify, request

from services.db import get_recommend

bp = Blueprint("recommend", __name__, url_prefix="/api/recommend")


@bp.route("")
def recommend():
    user_id = request.args.get("user_id", 0, type=int)
    limit = request.args.get("limit", 10, type=int)
    # TODO(Day2): rows = get_recommend(user_id, limit)  → 转成 items
    mock = {
        "items": [
            {"name": f"推荐{i}", "score": round(0.95 - i * 0.05, 2), "reason": "协同过滤"}
            for i in range(1, limit + 1)
        ]
    }
    return jsonify(mock)
