from flask import Blueprint

from api._response import ok, fail
from config import USE_REAL_DATA
from services.hive_client import query
from services.queries import (
    kpi_cards_sql, F_DAU, F_TOTAL_ORDERS, F_BUY_CONVERSION, F_AVG_PV,
)

bp = Blueprint("kpi", __name__, url_prefix="/api/kpi")


@bp.route("/cards")
def cards():
    if USE_REAL_DATA:
        try:
            rows = query(kpi_cards_sql()).to_dict("records")
            if not rows:
                return fail("no data", 404)
            today = rows[0]
            prev = rows[1] if len(rows) > 1 else None

            dau = int(today[F_DAU])
            dau_change = (
                (today[F_DAU] - prev[F_DAU]) / prev[F_DAU]
                if prev and prev[F_DAU] else 0.0
            )
            return ok({
                "dau": dau,
                "dau_change": round(float(dau_change), 4),
                "orders": int(today[F_TOTAL_ORDERS]),
                "conversion_rate": round(float(today[F_BUY_CONVERSION]), 4),
                "avg_pv": round(float(today[F_AVG_PV]), 2),
            })
        except Exception as e:
            return fail(str(e))

    # Mock：字段对齐 D 前端 api.js mockData.kpi
    return ok({
        "dau": 12345,
        "dau_change": -0.03,
        "orders": 8900,
        "orders_change": 0.061,
        "conversion_rate": 0.0382,
        "conversion_change": 0.005,
        "avg_pv": 8.5,
        "avg_pv_change": 0.024,
    })
