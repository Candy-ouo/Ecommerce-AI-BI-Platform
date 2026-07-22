#!/bin/bash
# run_dws_step1.sh — 按天分片填充 tmp_cat_user / tmp_platform_user
# 解决本地 Hadoop 内存不足导致单次 GROUP BY (category,date,user) 卡住的问题

set -e

DB="ecommerce_bi"

echo "== Step 0: 创建 tmp_cat_user / tmp_platform_user =="
hive -e "
USE ${DB};

DROP TABLE IF EXISTS tmp_cat_user;
CREATE TABLE tmp_cat_user (
    item_category    BIGINT,
    behavior_date    STRING,
    user_id          BIGINT,
    pv               BIGINT,
    fav              BIGINT,
    cart             BIGINT,
    buy              BIGINT
);

DROP TABLE IF EXISTS tmp_platform_user;
CREATE TABLE tmp_platform_user (
    behavior_date    STRING,
    user_id          BIGINT,
    pv               BIGINT,
    fav              BIGINT,
    cart             BIGINT,
    buy              BIGINT
);
"

# 从已成功生成的 dws_user_day 分区里拿日期列表（避免全表扫描 dwd_user_behavior）
DATES=$(hive -e "USE ${DB}; SHOW PARTITIONS dws_user_day;" 2>/dev/null | grep '^dt=' | sed 's/dt=//')

if [ -z "$DATES" ]; then
    echo "ERROR: 无法从 dws_user_day 获取日期分区，请确认 dws_user_day 已成功生成"
    exit 1
fi

echo "== 待处理日期: $DATES =="

for DT in $DATES; do
    echo "==> 处理日期 $DT"

    hive -e "
    USE ${DB};

    SET hive.exec.dynamic.partition.mode=nonstrict;
    SET mapreduce.map.memory.mb=4096;
    SET mapreduce.reduce.memory.mb=4096;
    SET mapreduce.map.java.opts=-Xmx3600m;
    SET mapreduce.reduce.java.opts=-Xmx3600m;

    INSERT INTO TABLE tmp_cat_user
    SELECT
        item_category,
        behavior_date,
        user_id,
        SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS pv,
        SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS fav,
        SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS cart,
        SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy
    FROM dwd_user_behavior
    WHERE behavior_date = '${DT}'
    GROUP BY item_category, behavior_date, user_id;
    "

    hive -e "
    USE ${DB};

    SET hive.exec.dynamic.partition.mode=nonstrict;
    SET mapreduce.map.memory.mb=2048;
    SET mapreduce.reduce.memory.mb=2048;
    SET mapreduce.map.java.opts=-Xmx1600m;
    SET mapreduce.reduce.java.opts=-Xmx1600m;

    SET mapreduce.map.memory.mb=4096;
    SET mapreduce.reduce.memory.mb=4096;
    SET mapreduce.map.java.opts=-Xmx3600m;
    SET mapreduce.reduce.java.opts=-Xmx3600m;

    INSERT INTO TABLE tmp_platform_user
    SELECT
        behavior_date,
        user_id,
        SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS pv,
        SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS fav,
        SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS cart,
        SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy
    FROM dwd_user_behavior
    WHERE behavior_date = '${DT}'
    GROUP BY behavior_date, user_id;
    "
done

echo "== Step 1 完成，开始跑 Step 2 聚合 =="
hive -f /tmp/03_dws_agg_part34.sql

echo "== 全部完成 =="
