-- ============================================================
-- 04_ads_app.sql — ADS 应用层：面向大屏/API 的即查即用指标表
-- 负责：A — 数仓架构师
-- 依赖：DWS 层数据已就绪
-- 说明：这些表直接支撑 C 的 REST API 和 D 的大屏图表
-- ============================================================

USE ecommerce_bi;

SET hive.exec.dynamic.partition.mode=nonstrict;
SET mapreduce.map.memory.mb=1024;
SET mapreduce.reduce.memory.mb=1024;
SET mapreduce.map.java.opts=-Xmx800m;
SET mapreduce.reduce.java.opts=-Xmx800m;

-- ----------------------------
-- 1. 每日 KPI 汇总表 ads_daily_kpi
--    面向大屏 KPI 指标卡（F3.1）
--    API: GET /api/kpi/cards
-- ----------------------------
DROP TABLE IF EXISTS ads_daily_kpi;
CREATE TABLE ads_daily_kpi (
    dau              BIGINT   COMMENT '日活跃用户数 DAU',
    dau_change       DOUBLE   COMMENT 'DAU 环比变化率',
    total_pv         BIGINT   COMMENT '全站总 PV',
    pv_change        DOUBLE   COMMENT 'PV 环比变化率',
    total_orders     BIGINT   COMMENT '订单量（购买行为数）',
    orders_change    DOUBLE   COMMENT '订单量环比变化率',
    buy_conversion   DOUBLE   COMMENT '全站购买转化率',
    conversion_change DOUBLE  COMMENT '转化率环比变化率',
    avg_pv           DOUBLE   COMMENT '人均 PV',
    avg_pv_change    DOUBLE   COMMENT '人均 PV 环比变化率'
)
COMMENT 'ADS 每日 KPI 汇总 — 供大屏 KPI 卡片直接查询'
PARTITIONED BY (dt STRING COMMENT '分区日期 YYYY-MM-DD')
STORED AS ORC;

INSERT OVERWRITE TABLE ads_daily_kpi PARTITION (dt)
SELECT
    curr.total_uv                                                                              AS dau,
    ROUND((curr.total_uv - prev.total_uv) * 1.0 / NULLIF(prev.total_uv, 0), 4)                AS dau_change,
    curr.total_pv                                                                              AS total_pv,
    ROUND((curr.total_pv - prev.total_pv) * 1.0 / NULLIF(prev.total_pv, 0), 4)                AS pv_change,
    curr.total_buy                                                                             AS total_orders,
    ROUND((curr.total_buy - prev.total_buy) * 1.0 / NULLIF(prev.total_buy, 0), 4)             AS orders_change,
    curr.buy_conversion                                                                        AS buy_conversion,
    ROUND((curr.buy_conversion - prev.buy_conversion), 4)                                      AS conversion_change,
    ROUND(curr.total_pv * 1.0 / NULLIF(curr.total_uv, 0), 2)                                  AS avg_pv,
    ROUND((curr.total_pv * 1.0 / NULLIF(curr.total_uv, 0)
         - prev.total_pv * 1.0 / NULLIF(prev.total_uv, 0))
         / NULLIF(prev.total_pv * 1.0 / NULLIF(prev.total_uv, 0), 0), 4)                      AS avg_pv_change,
    curr.dt                                                                                    AS dt
FROM dws_platform_day curr
LEFT JOIN dws_platform_day prev
    ON prev.dt = DATE_SUB(curr.dt, 1)
WHERE curr.dt IS NOT NULL;

-- ----------------------------
-- 2. 转化漏斗表 ads_funnel
--    全站 + 各类目漏斗各环节人数
--    API: GET /api/funnel
-- ----------------------------
DROP TABLE IF EXISTS ads_funnel;
CREATE TABLE ads_funnel (
    item_category    BIGINT   COMMENT '类目ID（NULL 表示全站汇总）',
    level_name       STRING   COMMENT '漏斗层级：全站 / 类目名称',
    pv_users         BIGINT   COMMENT '浏览用户数',
    fav_users        BIGINT   COMMENT '收藏用户数',
    cart_users       BIGINT   COMMENT '加购用户数',
    buy_users        BIGINT   COMMENT '购买用户数',
    pv_to_fav_rate   DOUBLE   COMMENT '浏览→收藏转化率',
    fav_to_cart_rate DOUBLE   COMMENT '收藏→加购转化率',
    cart_to_buy_rate DOUBLE   COMMENT '加购→购买转化率',
    pv_to_buy_rate   DOUBLE   COMMENT '浏览→购买 整体转化率'
)
COMMENT 'ADS 转化漏斗 — 全站+各类目漏斗各环节人数与转化率'
PARTITIONED BY (dt STRING COMMENT '分区日期 YYYY-MM-DD')
STORED AS ORC;

INSERT OVERWRITE TABLE ads_funnel PARTITION (dt)
-- 全站漏斗
SELECT
    NULL                                              AS item_category,
    '全站'                                            AS level_name,
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
    behavior_date                                     AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY behavior_date

UNION ALL

-- 各类目漏斗
SELECT
    item_category,
    CAST(item_category AS STRING)                     AS level_name,
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
    behavior_date                                     AS dt
FROM dwd_user_behavior
WHERE behavior_date IS NOT NULL
GROUP BY item_category, behavior_date;

-- ----------------------------
-- 3. 类目 TopN 排行表 ads_category_topn
--    按 PV 热度 / 购买热度排行
--    API: GET /api/top/items?limit=10&sort_by=pv
-- ----------------------------
DROP TABLE IF EXISTS ads_category_topn;
CREATE TABLE ads_category_topn (
    item_category    BIGINT   COMMENT '类目ID',
    pv_cnt           BIGINT   COMMENT '浏览量',
    buy_cnt          BIGINT   COMMENT '购买量',
    uv               BIGINT   COMMENT '独立访客',
    buy_conversion   DOUBLE   COMMENT '购买转化率',
    pv_rank          INT      COMMENT 'PV 热度排名',
    buy_rank         INT      COMMENT '购买热度排名'
)
COMMENT 'ADS 类目 TopN 排行 — 供柱状图直接查询'
PARTITIONED BY (dt STRING COMMENT '分区日期 YYYY-MM-DD')
STORED AS ORC;

INSERT OVERWRITE TABLE ads_category_topn PARTITION (dt)
SELECT
    item_category,
    pv_cnt,
    buy_cnt,
    uv,
    buy_conversion,
    ROW_NUMBER() OVER (ORDER BY pv_cnt DESC)  AS pv_rank,
    ROW_NUMBER() OVER (ORDER BY buy_cnt DESC) AS buy_rank,
    dt
FROM dws_category_day
WHERE dt IS NOT NULL;

-- ----------------------------
-- 4. 用户 RFM 分层表 ads_user_rfm
--    R/F/M 原始值 + 分箱得分 + 8类分层标签
--    API: GET /api/rfm/dist
--    注：B 的 rfm_model.py 也会产出 RFM 到 MySQL，
--        此表作为 Hive 侧的一致性备份，供 SQL 直接查询
-- ----------------------------
DROP TABLE IF EXISTS ads_user_rfm;
CREATE TABLE ads_user_rfm (
    user_id         BIGINT   COMMENT '用户ID',
    r_value         INT      COMMENT 'R值：距统计截止日期的天数',
    f_value         INT      COMMENT 'F值：统计周期内购买次数',
    m_value         INT      COMMENT 'M值：购买涉及的去重商品数（替代金额）',
    r_score         INT      COMMENT 'R分箱得分：1=低(差) 2=中 3=高(好)',
    f_score         INT      COMMENT 'F分箱得分：1=低 2=中 3=高',
    m_score         INT      COMMENT 'M分箱得分：1=低 2=中 3=高',
    rfm_group       STRING   COMMENT 'RFM 8类分层标签',
    rfm_label_cn    STRING   COMMENT 'RFM 8类中文标签'
)
COMMENT 'ADS 用户 RFM 分层 — 供饼图直接查询'
PARTITIONED BY (dt STRING COMMENT '分区日期 YYYY-MM-DD（统计截止日）')
STORED AS ORC;

INSERT OVERWRITE TABLE ads_user_rfm PARTITION (dt)
SELECT
    user_id,
    r_value,
    f_value,
    m_value,
    r_score,
    f_score,
    m_score,
    CONCAT(CAST(r_score AS STRING), CAST(f_score AS STRING), CAST(m_score AS STRING)) AS rfm_group,
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
FROM (
    SELECT
        user_id,
        r_value,
        f_value,
        m_value,
        4 - NTILE(3) OVER (ORDER BY r_value ASC) AS r_score,
        NTILE(3) OVER (ORDER BY f_value) AS f_score,
        NTILE(3) OVER (ORDER BY m_value) AS m_score
    FROM (
        SELECT
            user_id,
            DATEDIFF('2014-12-18', MAX(behavior_date)) AS r_value,
            SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS f_value,
            COUNT(DISTINCT CASE WHEN behavior_type = 4 THEN item_id END) AS m_value
        FROM dwd_user_behavior
        WHERE behavior_date IS NOT NULL
        GROUP BY user_id
    ) rfm_raw
) rfm_scored;

-- ----------------------------
-- 5. 用户推荐结果表 ads_user_recommend
--    来源：B 的 recommender.py 产出 CSV → HDFS → 导入
--    API: GET /api/recommend
-- ----------------------------
DROP TABLE IF EXISTS ads_user_recommend;
CREATE TABLE ads_user_recommend (
    user_id         BIGINT   COMMENT '用户ID',
    item_id         BIGINT   COMMENT '推荐商品ID',
    score           DOUBLE   COMMENT '推荐分数（余弦相似度）',
    reason          STRING   COMMENT '推荐理由'
)
COMMENT 'ADS 用户个性化推荐 — B 的 Item-CF 模型产出'
PARTITIONED BY (dt STRING COMMENT '分区日期')
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
TBLPROPERTIES ('skip.header.line.count'='1');

-- 加载数据：
-- docker cp data/recommend_result.csv tier4_stu_namenode:/tmp/
-- docker exec tier4_stu_namenode hdfs dfs -put -f /tmp/recommend_result.csv /user/data/
-- docker exec tier4_stu_hiveserver2 hive -e "USE ecommerce_bi; LOAD DATA INPATH '/user/data/recommend_result.csv' OVERWRITE INTO TABLE ads_user_recommend PARTITION (dt='2014-12-18');"

-- ----------------------------
-- 6. 验证
-- ----------------------------
SELECT 'ads_daily_kpi'     AS table_name, COUNT(*) AS row_cnt, MAX(dt) AS latest_dt FROM ads_daily_kpi
UNION ALL
SELECT 'ads_funnel',        COUNT(*), MAX(dt) FROM ads_funnel
UNION ALL
SELECT 'ads_category_topn', COUNT(*), MAX(dt) FROM ads_category_topn
UNION ALL
SELECT 'ads_user_rfm',         COUNT(*), MAX(dt) FROM ads_user_rfm
UNION ALL
SELECT 'ads_user_recommend',   COUNT(*), MAX(dt) FROM ads_user_recommend;
