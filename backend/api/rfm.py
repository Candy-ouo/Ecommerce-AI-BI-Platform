"""GET /api/rfm/dist —— RFM 用户分层占比。

跟 KPI/趋势/漏斗接口统一，直读 A 的 Hive ads_user_rfm 表。
B→MySQL→C 的绕路已去掉，A 的 Hive 表用 NTILE(3) 打好了 9 类标签。
"""
from flask import Blueprint, jsonify

from services.hive_client import query

bp = Blueprint("rfm", __name__, url_prefix="/api/rfm")


@bp.route("/dist")
def dist():
    try:
        df = query("""
            SELECT rfm_label_cn, COUNT(*) AS cnt
            FROM ads_user_rfm
            WHERE dt = '2014-12-18'
            GROUP BY rfm_label_cn
            ORDER BY cnt DESC
        """)
        return jsonify({
            "labels": df.iloc[:, 0].tolist(),
            "counts": df.iloc[:, 1].astype(int).tolist(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
