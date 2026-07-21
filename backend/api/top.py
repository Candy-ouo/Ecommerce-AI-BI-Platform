from flask import Blueprint, request

from api._response import ok, fail
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
                {"item_id": str(r["item_id"]), "name": str(r["item_id"]), "pv": int(r["pv"]), "fav": int(r["fav"]), "buy": int(r["buy"])}
                for r in df.to_dict("records")
            ]
            return ok({"items": items})
        except Exception as e:
            return fail(str(e))

    return ok({
        "items": [
            {
                "item_id": f"item_{i}",
                "name": f"item_{i}",
                "pv": 10000 - i * 90,
                "fav": 6000 - i * 50,
                "buy": 3000 - i * 25,
            }
            for i in range(1, limit + 1)
        ]
    })
