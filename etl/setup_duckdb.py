"""从 sample_10k.csv 构建完整 DuckDB 数仓（ODS → DWD → DWS → ADS）。

用法：python etl/setup_duckdb.py

产出：data/processed/ecommerce.duckdb
使用：改 .env 中 DB_ENGINE=duckdb + USE_REAL_DATA=true
"""
import os
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import duckdb

# ── 路径 ──
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample" / "sample_10k.csv"
DUCKDB_PATH = PROJECT_ROOT / "data" / "processed" / "ecommerce.duckdb"
os.makedirs(DUCKDB_PATH.parent, exist_ok=True)

# ── 清理旧数据库 ──
if DUCKDB_PATH.exists():
    if not DUCKDB_PATH.parent.samefile(PROJECT_ROOT):
        DUCKDB_PATH.unlink()
        print(f"已删除旧数据库: {DUCKDB_PATH}")

conn = duckdb.connect(str(DUCKDB_PATH))
print(f"创建新数据库: {DUCKDB_PATH}")

# ============================================================
# Step 0: 加载 sample_10k.csv → 清洗 → 导入 ODS
# ============================================================
print("\n" + "=" * 60)
print("  Step 0: 加载 sample_10k.csv → 清洗 → ODS")
print("=" * 60)

df = pd.read_csv(SAMPLE_CSV, dtype=str)
print(f"  原始行数: {len(df):,}")

# 列映射: sample 列名 → ODS 列名
# sample: user_id, item_id, behavior_type, user_geohash, user_item_category, time, item_geohash, item_item_category
# ODS: user_id, item_id, behavior_type, behavior_type_cn, user_geohash, item_category, behavior_date, behavior_hour

BEHAVIOR_MAP = {1: "浏览", 2: "收藏", 3: "加购", 4: "购买"}
VALID_TYPES = {1, 2, 3, 4}

# 解析行为类型
df["behavior_type_int"] = pd.to_numeric(df["behavior_type"], errors="coerce")
invalid_type = ~df["behavior_type_int"].isin(VALID_TYPES)
print(f"  过滤无效行为类型: {invalid_type.sum()} 行")
df = df[~invalid_type].copy()

# 解析时间
df["time_dt"] = pd.to_datetime(df["time"], format="%Y-%m-%d %H", errors="coerce")
invalid_time = df["time_dt"].isna()
print(f"  过滤无效时间: {invalid_time.sum()} 行")
df = df[~invalid_time].copy()

# 过滤日期范围
in_range = (df["time_dt"] >= pd.Timestamp("2014-11-18")) & (df["time_dt"] <= pd.Timestamp("2014-12-18 23"))
print(f"  过滤日期越界: {(~in_range).sum()} 行")
df = df[in_range].copy()

# 构建 ODS 列
df["behavior_type_cn"] = df["behavior_type_int"].map(BEHAVIOR_MAP)
df["behavior_date"] = df["time_dt"].dt.strftime("%Y-%m-%d")
df["behavior_hour"] = df["time_dt"].dt.hour.astype(int)
df["item_category"] = df["user_item_category"].fillna("0")

# 输出
ods_cols = ["user_id", "item_id", "behavior_type_int", "behavior_type_cn", "user_geohash", "item_category", "behavior_date", "behavior_hour"]
ods_df = df[ods_cols].rename(columns={"behavior_type_int": "behavior_type"})
ods_df["user_id"] = ods_df["user_id"].astype("int64")
ods_df["item_id"] = ods_df["item_id"].astype("int64")
ods_df["item_category"] = ods_df["item_category"].astype("int64")
ods_df["behavior_type"] = ods_df["behavior_type"].astype("int32")
ods_df["behavior_hour"] = ods_df["behavior_hour"].astype("int32")

print(f"  清洗后行数: {len(ods_df):,}")

# 行为类型分布
for k, v in BEHAVIOR_MAP.items():
    cnt = (ods_df["behavior_type"] == k).sum()
    pct = cnt / len(ods_df) * 100 if len(ods_df) > 0 else 0
    print(f"    {v}: {cnt} ({pct:.1f}%)")

# ── 注册 ODS 表 ──
conn.register("ods_user_behavior", ods_df)
conn.execute("CREATE TABLE ods_user_behavior AS SELECT * FROM ods_user_behavior")

# 同时也构建 ods_item_info（从行为表中去重提取）
conn.execute("""
CREATE TABLE ods_item_info AS
SELECT DISTINCT item_id, item_category
FROM ods_user_behavior
WHERE item_category IS NOT NULL AND item_category > 0
""")

print(f"  ods_user_behavior: {conn.execute('SELECT COUNT(*) FROM ods_user_behavior').fetchone()[0]:,} 行")
print(f"  ods_item_info: {conn.execute('SELECT COUNT(*) FROM ods_item_info').fetchone()[0]:,} 行")

# ============================================================
# Step 1: DWD 层
# ============================================================
print("\n" + "=" * 60)
print("  Step 1: 构建 DWD 明细层")
print("=" * 60)

conn.execute("""
CREATE TABLE dwd_user_behavior AS
SELECT
    ub.user_id,
    ub.item_id,
    ub.behavior_type,
    ub.behavior_type_cn,
    ub.user_geohash,
    ub.item_category,
    ub.behavior_date,
    ub.behavior_hour,
    ub.behavior_date AS dt
FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY user_id, item_id, behavior_type, behavior_date, behavior_hour
               ORDER BY behavior_date
           ) AS rn
    FROM ods_user_behavior
) ub
WHERE ub.rn = 1
""")

print(f"  dwd_user_behavior: {conn.execute('SELECT COUNT(*) FROM dwd_user_behavior').fetchone()[0]:,} 行")
print(f"  日期范围: {conn.execute('SELECT MIN(behavior_date), MAX(behavior_date) FROM dwd_user_behavior').fetchone()}")
print(f"  类目数: {conn.execute('SELECT COUNT(DISTINCT item_category) FROM dwd_user_behavior').fetchone()[0]}")

# ============================================================
# Step 2: DWS 层
# ============================================================
print("\n" + "=" * 60)
print("  Step 2: 构建 DWS 汇总层")
print("=" * 60)

# dws_user_day: 用户日粒度
print("  构建 dws_user_day ...")
conn.execute("""
CREATE TABLE dws_user_day AS
SELECT
    user_id,
    SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS pv_cnt,
    SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy_cnt,
    COUNT(DISTINCT behavior_hour) AS active_hours,
    behavior_date AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY user_id, behavior_date
""")
print(f"    用户数: {conn.execute('SELECT COUNT(*) FROM dws_user_day').fetchone()[0]:,}")

# dws_item_day: 商品日粒度
print("  构建 dws_item_day ...")
conn.execute("""
CREATE TABLE dws_item_day AS
SELECT
    item_id,
    SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS pv_cnt,
    SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy_cnt,
    CASE
        WHEN SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) > 0
        THEN ROUND(SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) * 1.0
             / SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END), 4)
        ELSE 0
    END AS buy_conversion,
    behavior_date AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY item_id, behavior_date
""")
print(f"    商品数: {conn.execute('SELECT COUNT(*) FROM dws_item_day').fetchone()[0]:,}")

# dws_category_day: 类目日粒度
print("  构建 dws_category_day ...")
conn.execute("""
CREATE TABLE dws_category_day AS
SELECT
    item_category,
    SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS pv_cnt,
    SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy_cnt,
    COUNT(DISTINCT user_id) AS uv,
    CASE
        WHEN COUNT(DISTINCT user_id) > 0
        THEN ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) * 1.0
             / NULLIF(COUNT(DISTINCT user_id), 0), 4)
        ELSE 0
    END AS buy_conversion,
    behavior_date AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY item_category, behavior_date
""")
print(f"    类目数: {conn.execute('SELECT COUNT(*) FROM dws_category_day').fetchone()[0]:,}")

# dws_platform_day: 全站日粒度
print("  构建 dws_platform_day ...")
conn.execute("""
CREATE TABLE dws_platform_day AS
SELECT
    COUNT(DISTINCT user_id) AS total_uv,
    SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS total_pv,
    SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS total_fav,
    SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS total_cart,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS total_buy,
    CASE
        WHEN COUNT(DISTINCT user_id) > 0
        THEN ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) * 1.0
             / NULLIF(COUNT(DISTINCT user_id), 0), 4)
        ELSE 0
    END AS buy_conversion,
    behavior_date AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY behavior_date
""")
print(f"    天数: {conn.execute('SELECT COUNT(*) FROM dws_platform_day').fetchone()[0]}")

# ============================================================
# Step 3: ADS 层
# ============================================================
print("\n" + "=" * 60)
print("  Step 3: 构建 ADS 应用层")
print("=" * 60)

# ads_daily_kpi: 每日 KPI 汇总（带环比）
print("  构建 ads_daily_kpi ...")
conn.execute("""
CREATE TABLE ads_daily_kpi AS
SELECT
    curr.total_uv AS dau,
    ROUND((curr.total_uv - COALESCE(prev.total_uv, 0)) * 1.0 / NULLIF(prev.total_uv, 0), 4) AS dau_change,
    curr.total_pv AS total_pv,
    ROUND((curr.total_pv - COALESCE(prev.total_pv, 0)) * 1.0 / NULLIF(prev.total_pv, 0), 4) AS pv_change,
    curr.total_buy AS total_orders,
    ROUND((curr.total_buy - COALESCE(prev.total_buy, 0)) * 1.0 / NULLIF(prev.total_buy, 0), 4) AS orders_change,
    curr.buy_conversion,
    ROUND(curr.buy_conversion - COALESCE(prev.buy_conversion, 0), 4) AS conversion_change,
    ROUND(curr.total_pv * 1.0 / NULLIF(curr.total_uv, 0), 2) AS avg_pv,
    CASE
        WHEN prev.total_uv IS NOT NULL AND prev.total_uv > 0
        THEN ROUND((curr.total_pv * 1.0 / NULLIF(curr.total_uv, 0)
                  - prev.total_pv * 1.0 / NULLIF(prev.total_uv, 0))
                  / NULLIF(prev.total_pv * 1.0 / NULLIF(prev.total_uv, 0), 0), 4)
        ELSE 0
    END AS avg_pv_change,
    curr.dt
FROM dws_platform_day curr
LEFT JOIN dws_platform_day prev
    ON prev.dt = (curr.dt::DATE - INTERVAL 1 DAY)::VARCHAR
WHERE curr.dt IS NOT NULL
ORDER BY curr.dt
""")
kpids = conn.execute("SELECT MIN(dt), MAX(dt), COUNT(*) FROM ads_daily_kpi").fetchone()
print(f"    日期范围: {kpids[0]} ~ {kpids[1]}, 共 {kpids[2]} 天")

# ads_funnel: 转化漏斗
print("  构建 ads_funnel ...")
conn.execute("""
CREATE TABLE ads_funnel AS
-- 全站漏斗
SELECT
    NULL AS item_category,
    '全站' AS level_name,
    COUNT(DISTINCT CASE WHEN behavior_type = 1 THEN user_id END) AS pv_users,
    COUNT(DISTINCT CASE WHEN behavior_type = 2 THEN user_id END) AS fav_users,
    COUNT(DISTINCT CASE WHEN behavior_type = 3 THEN user_id END) AS cart_users,
    COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) AS buy_users,
    ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 2 THEN user_id END) * 1.0
        / NULLIF(COUNT(DISTINCT CASE WHEN behavior_type = 1 THEN user_id END), 0), 4) AS pv_to_fav_rate,
    ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 3 THEN user_id END) * 1.0
        / NULLIF(COUNT(DISTINCT CASE WHEN behavior_type = 2 THEN user_id END), 0), 4) AS fav_to_cart_rate,
    ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) * 1.0
        / NULLIF(COUNT(DISTINCT CASE WHEN behavior_type = 3 THEN user_id END), 0), 4) AS cart_to_buy_rate,
    ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) * 1.0
        / NULLIF(COUNT(DISTINCT CASE WHEN behavior_type = 1 THEN user_id END), 0), 4) AS pv_to_buy_rate,
    behavior_date AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY behavior_date

UNION ALL

-- 各类目漏斗
SELECT
    item_category,
    CAST(item_category AS VARCHAR) AS level_name,
    COUNT(DISTINCT CASE WHEN behavior_type = 1 THEN user_id END) AS pv_users,
    COUNT(DISTINCT CASE WHEN behavior_type = 2 THEN user_id END) AS fav_users,
    COUNT(DISTINCT CASE WHEN behavior_type = 3 THEN user_id END) AS cart_users,
    COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) AS buy_users,
    ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 2 THEN user_id END) * 1.0
        / NULLIF(COUNT(DISTINCT CASE WHEN behavior_type = 1 THEN user_id END), 0), 4) AS pv_to_fav_rate,
    ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 3 THEN user_id END) * 1.0
        / NULLIF(COUNT(DISTINCT CASE WHEN behavior_type = 2 THEN user_id END), 0), 4) AS fav_to_cart_rate,
    ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) * 1.0
        / NULLIF(COUNT(DISTINCT CASE WHEN behavior_type = 3 THEN user_id END), 0), 4) AS cart_to_buy_rate,
    ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) * 1.0
        / NULLIF(COUNT(DISTINCT CASE WHEN behavior_type = 1 THEN user_id END), 0), 4) AS pv_to_buy_rate,
    behavior_date AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY item_category, behavior_date
ORDER BY dt
""")
print(f"    漏斗行数: {conn.execute('SELECT COUNT(*) FROM ads_funnel').fetchone()[0]}")

# ads_category_topn: 类目排行
print("  构建 ads_category_topn ...")
conn.execute("""
CREATE TABLE ads_category_topn AS
SELECT
    item_category,
    pv_cnt,
    buy_cnt,
    uv,
    buy_conversion,
    ROW_NUMBER() OVER (PARTITION BY dt ORDER BY pv_cnt DESC) AS pv_rank,
    ROW_NUMBER() OVER (PARTITION BY dt ORDER BY buy_cnt DESC) AS buy_rank,
    dt
FROM dws_category_day
WHERE dt IS NOT NULL
""")
print(f"    排行行数: {conn.execute('SELECT COUNT(*) FROM ads_category_topn').fetchone()[0]}")

# ads_user_rfm: 用户 RFM 分层
print("  构建 ads_user_rfm ...")
# DuckDB 不支持 DATEDIFF，用日期差计算
conn.execute("""
CREATE TABLE ads_user_rfm AS
WITH rfm_raw AS (
    SELECT
        user_id,
        ABS(DATEDIFF('day', MAX(behavior_date)::DATE, DATE '2014-12-18')) AS r_value,
        SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS f_value,
        COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN item_id END) AS m_value
    FROM dwd_user_behavior
    WHERE behavior_date IS NOT NULL
    GROUP BY user_id
),
rfm_scored AS (
    SELECT
        *,
        4 - NTILE(3) OVER (ORDER BY r_value ASC) AS r_score,
        NTILE(3) OVER (ORDER BY f_value) AS f_score,
        NTILE(3) OVER (ORDER BY m_value) AS m_score
    FROM rfm_raw
)
SELECT
    user_id,
    r_value,
    f_value,
    m_value,
    r_score,
    f_score,
    m_score,
    CAST(r_score AS VARCHAR) || CAST(f_score AS VARCHAR) || CAST(m_score AS VARCHAR) AS rfm_group,
    CASE
        WHEN f_value = 0 THEN '浏览型用户'
        WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN '重要价值用户'
        WHEN r_score >= 3 AND f_score >= 3 AND m_score <= 2 THEN '重要发展用户'
        WHEN r_score >= 3 AND f_score <= 2 AND m_score >= 3 THEN '重要保持用户'
        WHEN r_score >= 3 AND f_score <= 2 AND m_score <= 2 THEN '新锐潜力用户'
        WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3 THEN '重要挽留用户'
        WHEN r_score <= 2 AND f_score >= 3 AND m_score <= 2 THEN '一般价值用户'
        WHEN r_score <= 2 AND f_score <= 2 AND m_score >= 3 THEN '一般发展用户'
        WHEN r_score <= 2 AND f_score <= 2 AND m_score <= 2 THEN '低价值用户'
        ELSE '未知'
    END AS rfm_label_cn,
    '2014-12-18' AS dt
FROM rfm_scored
""")
rfm_cnt = conn.execute("SELECT COUNT(*) FROM ads_user_rfm").fetchone()[0]
print(f"    用户 RFM 分层: {rfm_cnt} 人")
labels = conn.execute("SELECT rfm_label_cn, COUNT(*) FROM ads_user_rfm GROUP BY rfm_label_cn ORDER BY 2 DESC").fetchall()
for l, c in labels:
    print(f"      {l}: {c} ({c/rfm_cnt*100:.1f}%)")

# ads_user_recommend: 用户推荐表（Mock：基于购买历史推荐同类热门商品）
print("  构建 ads_user_recommend ...")
conn.execute("""
CREATE TABLE ads_user_recommend AS
WITH user_purchase AS (
    SELECT DISTINCT user_id, item_category
    FROM dwd_user_behavior
    WHERE behavior_type = 4 AND item_category > 0
),
cat_popular AS (
    SELECT
        item_category,
        item_id,
        cnt,
        ROW_NUMBER() OVER (PARTITION BY item_category ORDER BY cnt DESC) AS rnk
    FROM (
        SELECT item_category, item_id, COUNT(*) AS cnt
        FROM dwd_user_behavior
        WHERE behavior_type = 1 AND item_category > 0
        GROUP BY item_category, item_id
    )
)
SELECT
    up.user_id,
    cp.item_id,
    ROUND(0.95 - cp.rnk * 0.05, 4) AS score,
    '协同过滤 + 兴趣相似度' AS reason
FROM user_purchase up
JOIN cat_popular cp ON up.item_category = cp.item_category AND cp.rnk <= 10
""")
rec_cnt = conn.execute("SELECT COUNT(*) FROM ads_user_recommend").fetchone()[0]
rec_users = conn.execute("SELECT COUNT(DISTINCT user_id) FROM ads_user_recommend").fetchone()[0]
print(f"    推荐记录: {rec_cnt} 条, 覆盖 {rec_users} 个用户")

# ============================================================
# Step 4: 验证
# ============================================================
print("\n" + "=" * 60)
print("  验证：所有表数据量")
print("=" * 60)

tables = [
    "ods_user_behavior", "ods_item_info",
    "dwd_user_behavior",
    "dws_user_day", "dws_item_day", "dws_category_day", "dws_platform_day",
    "ads_daily_kpi", "ads_funnel", "ads_category_topn", "ads_user_rfm", "ads_user_recommend",
]
for t in tables:
    cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    cols = conn.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{t}'").fetchall()
    print(f"  [OK] {t:30s} {cnt:>8,} 行, {len(cols)} 列")

conn.close()

print(f"\n{'=' * 60}")
print(f"  [OK] DukeDB build done!")
print(f"  File: {DUCKDB_PATH}")
print(f"{'=' * 60}")
print(f"\n下一步：")
print(f"  1. 修改 backend/.env：")
print(f"     DB_ENGINE=duckdb")
print(f"     USE_REAL_DATA=true")
print(f"  2. 重启后端：cd backend && python app.py")
print(f"  3. 测试：Invoke-RestMethod -Uri http://localhost:5000/api/kpi/cards -TimeoutSec 5")
