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
            # 注：数据集为脱敏 ID，无真实商品名称，name 降级为 "商品 {item_id}"
            items = [
                {"item_id": str(r["item_id"]), "name": f"商品 {r['item_id']}",
                 "pv": int(r["pv"]), "fav": int(r["fav"]), "buy": int(r["buy"])}
                for r in df.to_dict("records")
            ]
            return ok({"items": items})
        except Exception as e:
            return fail(str(e))

    # Mock：name 字段给前端展示用（真实数据为脱敏 ID，无商品名称）
    demos = [
        ("商品 A", 12580, 420), ("商品 B", 9850, 380), ("商品 C", 7620, 290),
        ("商品 D", 6450, 260), ("商品 E", 5380, 210), ("商品 F", 4250, 175),
        ("商品 G", 3890, 150), ("商品 H", 3560, 165), ("商品 I", 2980, 120),
        ("商品 J", 2650, 110), ("商品 K", 2200, 95), ("商品 L", 1850, 80),
        ("商品 M", 1500, 65), ("商品 N", 1200, 50), ("商品 O", 900, 35),
    ]
    return ok({
        "items": [
            {
                "item_id": f"item_{i}",
                "name": demos[i-1][0] if i <= len(demos) else f"商品_{i}",
                "pv": demos[i-1][1] - (i-1) * 60 if i <= len(demos) else 10000 - i * 90,
                "fav": 6000 - i * 50,
                "buy": demos[i-1][2] - (i-1) * 5 if i <= len(demos) else 3000 - i * 25,
            }
            for i in range(1, limit + 1)
        ]
    })
