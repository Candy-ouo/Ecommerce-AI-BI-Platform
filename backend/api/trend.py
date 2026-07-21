from flask import Blueprint, request

from api._response import ok, fail
from config import USE_REAL_DATA
from services.hive_client import query
from services.queries import trend_active_sql, F_DT, F_TOTAL_UV, F_TOTAL_PV

bp = Blueprint("trend", __name__, url_prefix="/api/trend")


def _fmt_date(d):
    # Hive dt 可能是 date 对象或 'YYYY-MM-DD' 字符串，统一转 MM-DD
    if hasattr(d, "strftime"):
        return d.strftime("%m-%d")
    s = str(d)
    return s[5:10] if len(s) >= 10 else s


@bp.route("/active")
def active():
    days = int(request.args.get("days", 7))
    if USE_REAL_DATA:
        try:
            df = query(trend_active_sql(days))
            df = df.sort_values(F_DT)
            dates = [_fmt_date(d) for d in df[F_DT]]
            dau = [int(x) for x in df[F_TOTAL_UV]]
            pv = [int(x) for x in df[F_TOTAL_PV]]
            return ok({"dates": dates, "dau": dau, "pv": pv})
        except Exception as e:
            return fail(str(e))

    return ok({
        "dates": ["07-14", "07-15", "07-16", "07-17", "07-18", "07-19", "07-20"][:days],
        "dau": [12000, 12500, 11800, 13100, 12900, 13400, 13050][:days],
        "pv": [96000, 99000, 94000, 102000, 100000, 105000, 103000][:days],
    })
