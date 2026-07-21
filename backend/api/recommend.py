"""GET /api/recommend?user_id=xxx —— 用户推荐列表。

Real 模式：读 MySQL 中 B 的 recommender.py 产出的推荐结果表。
USE_REAL_DATA=false 或不具备连接时返回 Mock。
"""
from flask import Blueprint, jsonify, request

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
                {"item_id": str(r["item_id"]), "score": round(float(r["score"]), 4)}
                for r in rows
            ]
            return jsonify({"items": items})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    mock = {
        "items": [
            {"item_id": f"rec_item_{i}", "score": round(0.95 - i * 0.05, 2)}
            for i in range(1, limit + 1)
        ]
    }
    return jsonify(mock)
