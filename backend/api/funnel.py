from flask import Blueprint, jsonify

from config import USE_REAL_DATA
from services.hive_client import query
from services.queries import funnel_sql

bp = Blueprint("funnel", __name__, url_prefix="/api/funnel")


@bp.route("")
def funnel():
    if USE_REAL_DATA:
        try:
            r = query(funnel_sql()).to_dict("records")[0]
            return jsonify({
                "pv": int(r["pv"]),
                "fav": int(r["fav"]),
                "cart": int(r["cart"]),
                "buy": int(r["buy"]),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    mock = {"pv": 100000, "fav": 35000, "cart": 20000, "buy": 8000}
    return jsonify(mock)
