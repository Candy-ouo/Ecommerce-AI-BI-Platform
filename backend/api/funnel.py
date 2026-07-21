from flask import Blueprint

from api._response import ok, fail
from config import USE_REAL_DATA
from services.hive_client import query
from services.queries import funnel_sql

bp = Blueprint("funnel", __name__, url_prefix="/api/funnel")


def _calc_rates(pv, fav, cart, buy):
    """计算各级转化率，分母为 0 时兜底 0。"""
    return {
        "pv_to_fav_rate": round(fav / pv, 4) if pv else 0,
        "fav_to_cart_rate": round(cart / fav, 4) if fav else 0,
        "cart_to_buy_rate": round(buy / cart, 4) if cart else 0,
        "pv_to_buy_rate": round(buy / pv, 4) if pv else 0,
    }


@bp.route("")
def funnel():
    if USE_REAL_DATA:
        try:
            r = query(funnel_sql()).to_dict("records")[0]
            pv, fav, cart, buy = int(r["pv"]), int(r["fav"]), int(r["cart"]), int(r["buy"])
            return ok({"pv": pv, "fav": fav, "cart": cart, "buy": buy, **_calc_rates(pv, fav, cart, buy)})
        except Exception as e:
            return fail(str(e))

    pv, fav, cart, buy = 100000, 35000, 20000, 8000
    return ok({"pv": pv, "fav": fav, "cart": cart, "buy": buy, **_calc_rates(pv, fav, cart, buy)})
