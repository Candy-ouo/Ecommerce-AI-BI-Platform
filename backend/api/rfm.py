"""GET /api/rfm/dist —— RFM 8 类用户占比。

Real 模式：读 MySQL 中 A/B 写入的 rfm 结果表。
USE_REAL_DATA=false 或不具备连接时返回 Mock。
"""
from flask import Blueprint, jsonify

from config import USE_REAL_DATA
from services.db import get_rfm

bp = Blueprint("rfm", __name__, url_prefix="/api/rfm")


@bp.route("/dist")
def dist():
    if USE_REAL_DATA:
        try:
            rows = get_rfm()
            labels = [r["label"] for r in rows]
            counts = [r["cnt"] for r in rows]
            return jsonify({"labels": labels, "counts": counts})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    mock = {
        "labels": ["重要价值", "重要发展", "重要保持", "重要挽留",
                   "一般价值", "一般发展", "一般保持", "一般挽留"],
        "counts": [1200, 800, 600, 400, 1500, 900, 700, 500],
    }
    return jsonify(mock)
