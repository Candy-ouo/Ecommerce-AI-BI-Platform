"""GET /api/report/latest + GET /api/report/history —— AI 晨报接口。

Real 模式：读 MySQL 中 B 的 morning_report.py 产出的晨报表。
USE_REAL_DATA=false 或不具备连接时返回 Mock。
"""
from flask import Blueprint, jsonify, request

from config import USE_REAL_DATA
from services.db import get_report_latest, get_report_history

bp = Blueprint("report", __name__, url_prefix="/api/report")


@bp.route("/latest")
def latest():
    if USE_REAL_DATA:
        try:
            row = get_report_latest()
            if row is None:
                return jsonify({"error": "no report yet"}), 404
            return jsonify({
                "date": str(row["report_date"]),
                "content": row["content"],
                "anomalies": _parse_anomalies(row.get("anomalies")),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    mock = {
        "date": "2014-12-18",
        "content": (
            "今日 DAU 12,345（环比 +3.2%），总订单 8,900 单。"
            "全站转化率 4.2%，较昨日提升 0.3 个百分点。"
            "数码品类表现突出，浏览量环比增长 15%，购买转化率达 5.8%。"
            "建议关注服饰品类的收藏加购率下降趋势。"
        ),
        "anomalies": ["数码品类销量增长 15%", "服饰品类收藏率下降 5%"],
    }
    return jsonify(mock)


@bp.route("/history")
def history():
    days = request.args.get("days", 7, type=int)

    if USE_REAL_DATA:
        try:
            rows = get_report_history(days)
            reports = [
                {
                    "date": str(r["report_date"]),
                    "content": r["content"],
                    "anomalies": _parse_anomalies(r.get("anomalies")),
                }
                for r in rows
            ]
            return jsonify(reports)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    mock = [
        {
            "date": "2014-12-18",
            "content": "今日 DAU 12,345（环比 +3.2%），总订单 8,900 单。全站转化率 4.2%。",
            "anomalies": ["数码品类销量增长 15%"],
        },
        {
            "date": "2014-12-17",
            "content": "今日 DAU 11,962（环比 -1.1%），总订单 8,720 单。全站转化率 3.9%。",
            "anomalies": [],
        },
        {
            "date": "2014-12-16",
            "content": "今日 DAU 12,100（环比 +2.5%），总订单 9,050 单。全站转化率 4.1%。",
            "anomalies": ["服饰品类购买转化下降 8%"],
        },
    ][:days]
    return jsonify(mock)


def _parse_anomalies(raw):
    """将 MySQL 中存储的 anomalies（可能是 JSON 字符串或逗号分隔）转为列表。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    import json
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [s.strip() for s in str(raw).split(",") if s.strip()]
