"""GET /api/rfm/dist —— RFM 用户分层占比。

真实模式直读 A 的 Hive ads_user_rfm 表（NTILE(3) 打好 9 类标签）。
Mock 模式返回 9 类用户分层分布样本数据。
"""
from flask import Blueprint

from api._response import ok, fail
from config import USE_REAL_DATA

bp = Blueprint("rfm", __name__, url_prefix="/api/rfm")


# Mock 9 类用户分层分布
_MOCK_RFM = {
    "labels": [
        "重要价值用户", "重要发展用户", "重要保持用户", "重要挽留用户",
        "一般价值用户", "一般发展用户", "新锐潜力用户", "低价值用户",
        "浏览型用户",
    ],
    "counts": [2800, 3500, 2200, 4000, 3100, 4200, 2900, 6200, 5100],
}


@bp.route("/dist")
def dist():
    if USE_REAL_DATA:
        from services.hive_client import query
        try:
            # 动态取最新分区日期
            dt_df = query("SELECT MAX(dt) FROM ads_user_rfm")
            latest_dt = dt_df.iloc[0, 0] if not dt_df.empty else "2014-12-18"
            df = query(f"""
                SELECT rfm_label_cn, COUNT(*) AS cnt
                FROM ads_user_rfm
                WHERE dt = '{latest_dt}'
                GROUP BY rfm_label_cn
                ORDER BY cnt DESC
            """)
            return ok({
                "labels": df.iloc[:, 0].tolist(),
                "counts": df.iloc[:, 1].astype(int).tolist(),
            })
        except Exception as e:
            return fail(str(e))
    else:
        return ok(_MOCK_RFM)
