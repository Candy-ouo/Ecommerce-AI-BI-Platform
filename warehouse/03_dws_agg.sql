-- ============================================================
-- 03_dws_agg.sql — DWS 汇总层：日粒度聚合
-- 负责：A — 数仓架构师
-- 依赖：DWD 层数据已就绪
-- ============================================================

USE ecommerce_bi;

SET hive.exec.dynamic.partition.mode=nonstrict;
SET mapreduce.map.memory.mb=1024;
SET mapreduce.reduce.memory.mb=1024;
SET mapreduce.map.java.opts=-Xmx800m;
SET mapreduce.reduce.java.opts=-Xmx800m;

-- ----------------------------
-- 1. 用户日行为汇总表 dws_user_day
--    每个用户每天的行为次数统计 + 活跃小时分布
--    需求依据：requirements.md 5.1
-- ----------------------------
DROP TABLE IF EXISTS dws_user_day;
CREATE TABLE dws_user_day (
    user_id          BIGINT   COMMENT '用户ID',
    pv_cnt           BIGINT   COMMENT '当日浏览次数',
    fav_cnt          BIGINT   COMMENT '当日收藏次数',
    cart_cnt         BIGINT   COMMENT '当日加购次数',
    buy_cnt          BIGINT   COMMENT '当日购买次数',
    active_hours     INT      COMMENT '当日活跃小时数（去重）'
)
COMMENT 'DWS 用户日粒度行为汇总'
PARTITIONED BY (dt STRING COMMENT '分区日期 YYYY-MM-DD')
STORED AS ORC;

INSERT OVERWRITE TABLE dws_user_day PARTITION (dt)
SELECT
    user_id,
    SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS pv_cnt,
    SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy_cnt,
    COUNT(DISTINCT behavior_hour)                        AS active_hours,
    behavior_date                                        AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY user_id, behavior_date;

-- ----------------------------
-- 2. 商品日指标表 dws_item_day
--    每个商品每天的 PV/收藏/加购/购买 + 购买转化率
--    需求依据：requirements.md 5.1
-- ----------------------------
DROP TABLE IF EXISTS dws_item_day;
CREATE TABLE dws_item_day (
    item_id          BIGINT   COMMENT '商品ID',
    pv_cnt           BIGINT   COMMENT '当日浏览量',
    fav_cnt          BIGINT   COMMENT '当日收藏量',
    cart_cnt         BIGINT   COMMENT '当日加购量',
    buy_cnt          BIGINT   COMMENT '当日购买量',
    buy_conversion   DOUBLE   COMMENT '购买转化率 = buy_cnt / pv_cnt'
)
COMMENT 'DWS 商品日粒度指标'
PARTITIONED BY (dt STRING COMMENT '分区日期 YYYY-MM-DD')
STORED AS ORC;

INSERT OVERWRITE TABLE dws_item_day PARTITION (dt)
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
GROUP BY item_id, behavior_date;

-- ----------------------------
-- 3. 类目日指标表 dws_category_day
--    每个类目每天的 PV/收藏/加购/购买/UV/转化率
--    需求依据：requirements.md 5.1
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
    SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS pv_cnt,
    SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy_cnt,
    COUNT(DISTINCT user_id)                            AS uv,
    CASE
        WHEN COUNT(DISTINCT user_id) > 0
        THEN ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) * 1.0
             / COUNT(DISTINCT user_id), 4)
        ELSE 0
    END AS buy_conversion,
    behavior_date AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY item_category, behavior_date;

-- ----------------------------
-- 4. 全站日指标表 dws_platform_day
--    每天全平台汇总指标
--    需求依据：requirements.md 5.1
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
    COUNT(DISTINCT user_id)   AS total_uv,
    SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS total_pv,
    SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS total_fav,
    SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS total_cart,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS total_buy,
    CASE
        WHEN COUNT(DISTINCT user_id) > 0
        THEN ROUND(COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN user_id END) * 1.0
             / COUNT(DISTINCT user_id), 4)
        ELSE 0
    END AS buy_conversion,
    behavior_date            AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY behavior_date;

-- ----------------------------
-- 5. 验证
-- ----------------------------
SELECT 'dws_user_day'      AS table_name, COUNT(*) AS row_cnt, MAX(dt) AS latest_dt FROM dws_user_day
UNION ALL
SELECT 'dws_item_day',      COUNT(*), MAX(dt) FROM dws_item_day
UNION ALL
SELECT 'dws_category_day',  COUNT(*), MAX(dt) FROM dws_category_day
UNION ALL
SELECT 'dws_platform_day',  COUNT(*), MAX(dt) FROM dws_platform_day;
