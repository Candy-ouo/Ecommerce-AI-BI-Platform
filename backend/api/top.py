from flask import Blueprint, jsonify, request

from config import USE_REAL_DATA
from services.hive_client import query
from services.queries import top_items_sql

bp = Blueprint("top", __name__, url_prefix="/api/top")


@bp.route("/items")
def items():
    limit = int(request.args.get("limit", 10))
    sort_by = request.args.get("sort_by", "pv")
    if USE_REAL_DATA:
        try:
            df = query(top_items_sql(limit, sort_by))
            items = [
                {"name": str(r["item_id"]), "pv": int(r["pv"]), "fav": int(r["fav"])}
                for r in df.to_dict("records")
            ]
            return jsonify({"items": items})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    mock = {
        "items": [
            {"name": f"商品{i}", "pv": 9000 - i * 100, "fav": 3000 - i * 80}
            for i in range(1, limit + 1)
        ]
    }
    return jsonify(mock)
