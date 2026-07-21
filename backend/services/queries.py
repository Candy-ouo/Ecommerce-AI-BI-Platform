"""分析查询 SQL（角色 C 负责）。

架构：C 直接查 A 在 Hive 建好的 **DWS/ADS 聚合表**（这些表是 A 按 C 的接口契约
专门建的，见需求文档 F2.5）。这样 C 不碰 ETL 细节，只依赖 A 在 Docs/schema.md
中确认的表名 / 字段名。

方言：HiveQL。以下常量已对齐 Docs/schema.md（2026-07-21 核对），
切 USE_REAL_DATA=true 即可直接运行。
"""

# ============================================================
# 表名 / 字段名常量（已对齐 Docs/schema.md + warehouse/*.sql）
# ============================================================
# A 建的聚合表（供 C 直接查）：
T_KPI = "ads_daily_kpi"            # 日KPI汇总：dau/orders/conversion_rate/avg_pv
T_PLATFORM_DAY = "dws_platform_day"  # 全站日粒度：uv(=dau)/pv/...
T_ITEM_DAY = "dws_item_day"        # 商品日粒度：item_id/pv/fav/cart/buy
T_FUNNEL = "ads_funnel"            # 全站漏斗：pv/fav/cart/buy
T_RFM = "ads_user_rfm"            # RFM 用户分层（A 路径 Hive 表）

# 字段名（已与 A 的 Docs/schema.md + warehouse/*.sql 对齐）
F_DT = "dt"

# ---- ads_daily_kpi 字段 ----
F_DAU = "dau"
F_TOTAL_ORDERS = "total_orders"
F_BUY_CONVERSION = "buy_conversion"
F_AVG_PV = "avg_pv"

# ---- dws_platform_day 字段 ----
F_TOTAL_UV = "total_uv"      # 日活（dws 层叫 total_uv）
F_TOTAL_PV = "total_pv"
F_TOTAL_BUY = "total_buy"    # 全站总购买量（订单量）

# ---- dws_category_day 字段（类目维度趋势） ----
F_CAT_UV = "uv"
F_CAT_PV = "pv_cnt"
F_CAT_BUY = "buy_cnt"
F_ITEM_CATEGORY = "item_category"

# ---- dws_item_day 字段 ----
F_ITEM = "item_id"
F_PV_CNT = "pv_cnt"
F_FAV_CNT = "fav_cnt"
F_CART_CNT = "cart_cnt"
F_BUY_CNT = "buy_cnt"

T_CATEGORY_DAY = "dws_category_day"  # 类目日粒度表（category 下钻用）

# ---- ads_funnel 字段 ----
F_PV_USERS = "pv_users"
F_FAV_USERS = "fav_users"
F_CART_USERS = "cart_users"
F_BUY_USERS = "buy_users"


def kpi_cards_sql():
    """最近 2 天 KPI（dau/total_orders/buy_conversion/avg_pv），环比由 Python 算。"""
    return f"""
    SELECT {F_DT}, {F_DAU}, {F_TOTAL_ORDERS}, {F_BUY_CONVERSION}, {F_AVG_PV}
    FROM {T_KPI}
    ORDER BY {F_DT} DESC
    LIMIT 2
    """


def trend_active_sql(days: int = 7, category: str = None):
    """最近 days 天全站日活 + PV + 订单量（升序喂折线图）。

    category 为空/"all" → 全站汇总（dws_platform_day）；
    传具体类目ID → 该类目维度趋势（dws_category_day）。
    """
    days = int(days)
    if category and category.lower() != "all":
        return f"""
        SELECT {F_DT}, {F_CAT_UV} AS {F_TOTAL_UV}, {F_CAT_PV} AS {F_TOTAL_PV},
               {F_CAT_BUY} AS {F_TOTAL_BUY}
        FROM {T_CATEGORY_DAY}
        WHERE {F_ITEM_CATEGORY} = {int(category)}
        ORDER BY {F_DT} DESC
        LIMIT {days}
        """
    return f"""
    SELECT {F_DT}, {F_TOTAL_UV}, {F_TOTAL_PV}, {F_TOTAL_BUY}
    FROM {T_PLATFORM_DAY}
    ORDER BY {F_DT} DESC
    LIMIT {days}
    """


def top_items_sql(limit: int = 10, sort_by: str = "pv"):
    """商品热度排行（按 pv/fav/buy 多日汇总）。sort_by 白名单防注入。"""
    if sort_by not in ("pv", "fav", "buy"):
        sort_by = "pv"
    return f"""
    SELECT {F_ITEM} AS item_id,
           SUM({F_PV_CNT}) AS pv,
           SUM({F_FAV_CNT}) AS fav,
           SUM({F_BUY_CNT}) AS buy
    FROM {T_ITEM_DAY}
    GROUP BY {F_ITEM}
    ORDER BY {sort_by} DESC
    LIMIT {int(limit)}
    """


def funnel_sql():
    """全站转化漏斗各环节人数（取最新一天的全站汇总行）。

    注：A 的 ads_funnel 含预计算转化率列，C 在 funnel.py 中自行计算并返回
    pv_to_fav_rate / fav_to_cart_rate / cart_to_buy_rate / pv_to_buy_rate。
    """
    return f"""
    SELECT {F_PV_USERS} AS pv, {F_FAV_USERS} AS fav, {F_CART_USERS} AS cart, {F_BUY_USERS} AS buy
    FROM {T_FUNNEL}
    WHERE item_category IS NULL
    ORDER BY {F_DT} DESC
    LIMIT 1
    """
