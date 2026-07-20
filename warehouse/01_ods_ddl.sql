-- ============================================================
-- 01_ods_ddl.sql — ODS 贴源层：建库、建表、加载数据
-- 负责：A — 数仓架构师
-- 依赖：E 产出清洗后的 CSV → data/processed/
--   - user_behavior_clean.csv
--   - item_info_clean.csv
-- ============================================================

-- ----------------------------
-- 0. 建库
-- ----------------------------
CREATE DATABASE IF NOT EXISTS ecommerce_bi
COMMENT '电商用户行为分析与AI智能BI平台 — 数据仓库';

USE ecommerce_bi;

-- ----------------------------
-- 1. ODS 用户行为表
--    来源：E 清洗后的 user_behavior_clean.csv
--    数据量：约 1225 万行
-- ----------------------------
DROP TABLE IF EXISTS ods_user_behavior;
CREATE TABLE ods_user_behavior (
    user_id          BIGINT   COMMENT '用户ID（脱敏）',
    item_id          BIGINT   COMMENT '商品ID（脱敏）',
    behavior_type    INT      COMMENT '行为类型：1=浏览 2=收藏 3=加购 4=购买',
    behavior_type_cn STRING   COMMENT '行为类型中文：浏览/收藏/加购/购买',
    user_geohash     STRING   COMMENT '用户地理位置哈希（约68%为空）',
    item_category    BIGINT   COMMENT '商品所属类目ID（脱敏）',
    behavior_date    STRING   COMMENT '行为日期，格式 YYYY-MM-DD',
    behavior_hour    INT      COMMENT '行为小时，取值 0-23'
)
COMMENT 'ODS 用户行为表 — E清洗后导入'
PARTITIONED BY (dt STRING COMMENT '分区日期，格式 YYYY-MM-DD')
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
TBLPROPERTIES ('skip.header.line.count'='1');

-- 加载数据（按日期分区逐天加载，示例加载全量到 2014-12-18 分区）
-- 实际执行时根据 E 产出的 CSV 路径调整
LOAD DATA INPATH '/user/data/user_behavior_clean.csv'
OVERWRITE INTO TABLE ods_user_behavior
PARTITION (dt='2014-12-18');

-- ----------------------------
-- 2. ODS 商品信息表
--    来源：E 清洗 + 去重后的 item_info_clean.csv
--    数据量：去重后约 31 万行（原始 48 万行含大量重复）
-- ----------------------------
DROP TABLE IF EXISTS ods_item_info;
CREATE TABLE ods_item_info (
    item_id        BIGINT   COMMENT '商品ID（脱敏，去重后约31万）',
    item_geohash   STRING   COMMENT '商品地理位置哈希（约64%为空）',
    item_category  BIGINT   COMMENT '商品所属类目ID（脱敏，去重后991个类目）'
)
COMMENT 'ODS 商品信息表 — E清洗去重后导入'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
TBLPROPERTIES ('skip.header.line.count'='1');

-- 加载数据
LOAD DATA INPATH '/user/data/item_info_clean.csv'
OVERWRITE INTO TABLE ods_item_info;

-- ----------------------------
-- 3. 验证
-- ----------------------------
SELECT 'ods_user_behavior' AS table_name, COUNT(*) AS row_cnt FROM ods_user_behavior
UNION ALL
SELECT 'ods_item_info'     AS table_name, COUNT(*) AS row_cnt FROM ods_item_info;
