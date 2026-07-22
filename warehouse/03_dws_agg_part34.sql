-- ============================================================
-- 03_dws_agg_part34.sql — DWS 汇总层：类目 + 全站日粒度聚合
-- 负责：A — 数仓架构师
-- 依赖：tmp_cat_user / tmp_platform_user 已由 run_dws_step1.sh 按天分片填充
-- ============================================================

USE ecommerce_bi;

SET hive.exec.dynamic.partition.mode=nonstrict;
SET mapreduce.map.memory.mb=4096;
SET mapreduce.reduce.memory.mb=4096;
SET mapreduce.map.java.opts=-Xmx3600m;
SET mapreduce.reduce.java.opts=-Xmx3600m;
SET mapreduce.map.speculative=false;
SET mapreduce.reduce.speculative=false;

-- ----------------------------
-- 3. 类目日指标表 dws_category_day
-- ----------------------------
DROP TABLE IF EXISTS dws_category_day;
CREATE TABLE dws_category_day (
    item_category    BIGINT   COMMENT '类目ID',
    pv_cnt           BIGINT   COMMENT '当日浏览量',
    fav_cnt          BIGINT   COMMENT '当日收藏量',
    cart_cnt         BIGINT   COMMENT '当日加购量',
    buy_cnt          BIGINT   COMMENT '当日购买量',
    uv               BIGINT   COMMENT '当日独立访客数',
    buy_conversion   DOUBLE   COMMENT '购买转化率 = buy_uv / uv'
)
COMMENT 'DWS 类目日粒度指标'
PARTITIONED BY (dt STRING COMMENT '分区日期 YYYY-MM-DD')
STORED AS ORC;

INSERT OVERWRITE TABLE dws_category_day PARTITION (dt)
SELECT
    item_category,
    SUM(pv)   AS pv_cnt,
    SUM(fav)  AS fav_cnt,
    SUM(cart) AS cart_cnt,
    SUM(buy)  AS buy_cnt,
    COUNT(1)  AS uv,
    CASE WHEN COUNT(1) > 0
         THEN ROUND(SUM(CASE WHEN buy > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(1), 4)
         ELSE 0
    END AS buy_conversion,
    behavior_date AS dt
FROM tmp_cat_user
GROUP BY item_category, behavior_date;

DROP TABLE IF EXISTS tmp_cat_user;

-- ----------------------------
-- 4. 全站日指标表 dws_platform_day
-- ----------------------------
DROP TABLE IF EXISTS dws_platform_day;
CREATE TABLE dws_platform_day (
    total_uv         BIGINT   COMMENT '全站日活跃用户数 DAU',
    total_pv         BIGINT   COMMENT '全站总浏览量',
    total_fav        BIGINT   COMMENT '全站总收藏量',
    total_cart       BIGINT   COMMENT '全站总加购量',
    total_buy        BIGINT   COMMENT '全站总购买量（订单量）',
    buy_conversion   DOUBLE   COMMENT '全站购买转化率 = buy_uv / total_uv'
)
COMMENT 'DWS 全站日粒度汇总指标'
PARTITIONED BY (dt STRING COMMENT '分区日期 YYYY-MM-DD')
STORED AS ORC;

INSERT OVERWRITE TABLE dws_platform_day PARTITION (dt)
SELECT
    COUNT(1)  AS total_uv,
    SUM(pv)   AS total_pv,
    SUM(fav)  AS total_fav,
    SUM(cart) AS total_cart,
    SUM(buy)  AS total_buy,
    CASE WHEN COUNT(1) > 0
         THEN ROUND(SUM(CASE WHEN buy > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(1), 4)
         ELSE 0
    END AS buy_conversion,
    behavior_date AS dt
FROM tmp_platform_user
GROUP BY behavior_date;

DROP TABLE IF EXISTS tmp_platform_user;

-- ----------------------------
-- 5. 验证
-- ----------------------------
SELECT 'dws_category_day'  AS table_name, COUNT(*) AS row_cnt, MAX(dt) AS latest_dt FROM dws_category_day
UNION ALL
SELECT 'dws_platform_day', COUNT(*), MAX(dt) FROM dws_platform_day;
