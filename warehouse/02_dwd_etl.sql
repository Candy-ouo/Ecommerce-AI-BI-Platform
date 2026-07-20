-- ============================================================
-- 02_dwd_etl.sql — DWD 明细层：两表Join、去重、标准化、维度表
-- 负责：A — 数仓架构师
-- 依赖：ODS 层数据已就绪
-- ============================================================

USE ecommerce_bi;

-- ----------------------------
-- 1. DWD 用户行为明细表
--    ODS 用户行为 LEFT JOIN ODS 商品信息 → 补全商品 geohash
--    去重：同一 user + item + behavior_type + time 去重
-- ----------------------------
DROP TABLE IF EXISTS dwd_user_behavior;
CREATE TABLE dwd_user_behavior (
    user_id           BIGINT   COMMENT '用户ID（脱敏）',
    item_id           BIGINT   COMMENT '商品ID（脱敏）',
    behavior_type     INT      COMMENT '行为类型编码：1=浏览 2=收藏 3=加购 4=购买',
    behavior_type_cn  STRING   COMMENT '行为类型中文',
    user_geohash      STRING   COMMENT '用户地理位置哈希',
    item_geohash      STRING   COMMENT '商品地理位置哈希（来自商品信息表）',
    item_category     BIGINT   COMMENT '商品所属类目ID（来自行为表，以行为表为准）',
    behavior_date     STRING   COMMENT '行为日期 YYYY-MM-DD',
    behavior_hour     INT      COMMENT '行为小时 0-23'
)
COMMENT 'DWD 用户行为明细 — 两表Join + 去重 + 标准化'
PARTITIONED BY (dt STRING COMMENT '分区日期 YYYY-MM-DD')
STORED AS PARQUET;

INSERT OVERWRITE TABLE dwd_user_behavior PARTITION (dt)
SELECT
    ub.user_id,
    ub.item_id,
    ub.behavior_type,
    CASE ub.behavior_type
        WHEN 1 THEN '浏览'
        WHEN 2 THEN '收藏'
        WHEN 3 THEN '加购'
        WHEN 4 THEN '购买'
        ELSE '未知'
    END                         AS behavior_type_cn,
    ub.user_geohash,
    it.item_geohash,
    ub.item_category,
    ub.behavior_date,
    ub.behavior_hour,
    ub.behavior_date            AS dt
FROM (
    -- 子查询：按 (user_id, item_id, behavior_type, behavior_date, behavior_hour) 去重
    SELECT
        user_id,
        item_id,
        behavior_type,
        user_geohash,
        item_category,
        behavior_date,
        behavior_hour,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, item_id, behavior_type, behavior_date, behavior_hour
            ORDER BY behavior_date
        ) AS rn
    FROM ods_user_behavior
) ub
LEFT JOIN ods_item_info it
    ON ub.item_id = it.item_id
WHERE ub.rn = 1;

-- ----------------------------
-- 2. 商品维度表 dim_item
--    商品 ↔ 类目映射（来自商品信息表，已去重）
--    需求依据：requirements.md 5.1
-- ----------------------------
DROP TABLE IF EXISTS dim_item;
CREATE TABLE dim_item (
    item_id        BIGINT   COMMENT '商品ID（脱敏）',
    item_category  BIGINT   COMMENT '所属类目ID'
)
COMMENT 'DWD 商品维度表 — 商品↔类目映射'
STORED AS PARQUET;

INSERT OVERWRITE TABLE dim_item
SELECT
    item_id,
    item_category
FROM ods_item_info
WHERE item_id IS NOT NULL;

-- ----------------------------
-- 3. 类目维度表 dim_category
--    去重类目 + 活跃度标签
--    需求依据：requirements.md 5.1
-- ----------------------------
DROP TABLE IF EXISTS dim_category;
CREATE TABLE dim_category (
    item_category   BIGINT   COMMENT '类目ID（脱敏）',
    activity_label  STRING   COMMENT '活跃度标签：高活跃/中活跃/低活跃'
)
COMMENT 'DWD 类目维度表 — 去重类目 + 活跃度标签'
STORED AS PARQUET;

INSERT OVERWRITE TABLE dim_category
SELECT
    item_category,
    CASE
        WHEN COUNT(DISTINCT user_id) >= 1000 THEN '高活跃'
        WHEN COUNT(DISTINCT user_id) >= 100  THEN '中活跃'
        ELSE '低活跃'
    END AS activity_label
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY item_category;

-- ----------------------------
-- 4. 验证
-- ----------------------------
SELECT 'dwd_user_behavior' AS table_name, COUNT(*) AS row_cnt FROM dwd_user_behavior
UNION ALL
SELECT 'dim_item',          COUNT(*) FROM dim_item
UNION ALL
SELECT 'dim_category',      COUNT(*) FROM dim_category;
