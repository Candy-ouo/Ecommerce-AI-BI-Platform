"""分析查询 SQL（角色 C 负责）。

架构：C 直接查 A 在 Hive 建好的 **DWS/ADS 聚合表**（这些表是 A 按 C 的接口契约
专门建的，见需求文档 F2.5）。这样 C 不碰 ETL 细节，只依赖 A 在
SCHEMA_CHECKLIST.md 中确认的表名 / 字段名。

方言：HiveQL。所有表名 / 字段名是基于「C→D 接口契约（需求文档第七章）」的最佳假设，
待 A 确认后通常只改本文件顶部常量即可。

⚠️ 这是 Day1 起草的草稿，尚未对真实 Hive 跑过。Day2 拿到 A 的确认后微调常量。
"""

# ============================================================
# 待 A 确认的表名 / 字段名（Day2 核对 SCHEMA_CHECKLIST.md）
# ============================================================
# A 建的聚合表（供 C 直接查）：
T_KPI = "ads_daily_kpi"            # 日KPI汇总：dau/orders/conversion_rate/avg_pv
T_PLATFORM_DAY = "dws_platform_day"  # 全站日粒度：uv(=dau)/pv/...
T_ITEM_DAY = "dws_item_day"        # 商品日粒度：item_id/pv/fav/cart/buy
T_FUNNEL = "ads_funnel"            # 全站漏斗：pv/fav/cart/buy

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

# ---- dws_item_day 字段 ----
F_ITEM = "item_id"
F_PV_CNT = "pv_cnt"
F_FAV_CNT = "fav_cnt"
F_CART_CNT = "cart_cnt"
F_BUY_CNT = "buy_cnt"

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


def trend_active_sql(days: int = 7):
    """最近 days 天全站日活 + PV（升序喂折线图）。"""
    days = int(days)
    return f"""
    SELECT {F_DT}, {F_TOTAL_UV}, {F_TOTAL_PV}
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
    """全站转化漏斗各环节人数（取最新一天的全站行）。"""
    return f"""
    SELECT {F_PV_USERS} AS pv, {F_FAV_USERS} AS fav, {F_CART_USERS} AS cart, {F_BUY_USERS} AS buy
    FROM {T_FUNNEL}
    ORDER BY {F_DT} DESC
    LIMIT 1
    """
