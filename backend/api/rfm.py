"""GET /api/rfm/dist —— RFM 8 类用户占比。

数据来自 MySQL（B 的 rfm_model.py 产出、A 的 ADS 层写入），
当前返回 Mock，Day 2 后换成 services.db.get_rfm()。
"""
from flask import Blueprint, jsonify

from services.db import get_rfm

bp = Blueprint("rfm", __name__, url_prefix="/api/rfm")


@bp.route("/dist")
def dist():
    # TODO(Day2): rows = get_rfm()  → 转成 labels/counts
    mock = {
        "labels": ["重要价值", "重要发展", "重要保持", "重要挽留",
                   "一般价值", "一般发展", "一般保持", "一般挽留"],
        "counts": [1200, 800, 600, 400, 1500, 900, 700, 500],
    }
    return jsonify(mock)
