# 数据仓库表结构文档

> **负责人：A — 数仓架构师**
> **下游使用者：B（NL2SQL Prompt 构建）+ C（API SQL 查询编写）**
> **最后更新：2026-07-21**
> **依据：requirements.md 5.1 数据仓库设计**

---

## 一、分层概览

```
ADS 应用层  ←── C 的 API 直接查询这层
  ↑
DWS 汇总层  ←── C 的复杂查询可查这层
  ↑
DWD 明细层  ←── 干净、关联好的明细数据
  ↑
ODS 贴源层  ←── E 清洗后直接导入
```

共 **14 张表**：

| 层级 | 表数 | 表名 |
|------|------|------|
| ODS  | 2    | `ods_user_behavior`, `ods_item_info` |
| DWD  | 3    | `dwd_user_behavior`, `dim_item`, `dim_category` |
| DWS  | 4    | `dws_user_day`, `dws_item_day`, `dws_category_day`, `dws_platform_day` |
| ADS  | 5    | `ads_daily_kpi`, `ads_funnel`, `ads_category_topn`, `ads_user_rfm`, `ads_user_recommend` |

---

## 二、ODS 贴源层

### 2.1 ods_user_behavior — 用户行为表

**来源**：E 清洗后的 `user_behavior_clean.csv`，约 1225 万行
**分区**：`dt`（格式 `YYYY-MM-DD`，如 `2014-12-18`）

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| user_id | BIGINT | 用户ID（脱敏） | `98047837` |
| item_id | BIGINT | 商品ID（脱敏） | `232431562` |
| behavior_type | INT | 行为类型编码 | `1`=浏览, `2`=收藏, `3`=加购, `4`=购买 |
| behavior_type_cn | STRING | 行为类型中文 | `浏览` / `收藏` / `加购` / `购买` |
| user_geohash | STRING | 用户位置哈希（约68%为空） | `95q6awg` 或空字符串 |
| item_category | BIGINT | 商品所属类目ID（来自行为表） | `4245` |
| behavior_date | STRING | 行为日期 | `2014-12-06` |
| behavior_hour | INT | 行为小时（0-23） | `2` |
| dt | STRING | 分区字段 = behavior_date | `2014-12-06` |

### 2.2 ods_item_info — 商品信息表

**来源**：E 清洗去重后的 `item_info_clean.csv`，约 31 万行（原始 48 万行去重）
**分区**：无（维度表）

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| item_id | BIGINT | 商品ID（脱敏，去重后唯一） | `312051294` |
| item_geohash | STRING | 商品地理位置哈希（约64%为空） | `95qqd9w` 或空字符串 |
| item_category | BIGINT | 商品所属类目ID（991个去重类目） | `8270` |

---

## 三、DWD 明细层

### 3.1 dwd_user_behavior — 用户行为明细（核心表）

**说明**：ods_user_behavior LEFT JOIN ods_item_info，补全 item_geohash，去重
**分区**：`dt`

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| user_id | BIGINT | 用户ID | `98047837` |
| item_id | BIGINT | 商品ID | `232431562` |
| behavior_type | INT | 行为类型编码 | `1` / `2` / `3` / `4` |
| behavior_type_cn | STRING | 行为类型中文 | `浏览` / `收藏` / `加购` / `购买` |
| user_geohash | STRING | 用户位置哈希 | `95q6awg` |
| item_geohash | STRING | 商品位置哈希（来自商品表） | `95qqd9w` |
| item_category | BIGINT | 类目ID（以行为表为准） | `4245` |
| behavior_date | STRING | 行为日期 | `2014-12-06` |
| behavior_hour | INT | 行为小时 0-23 | `2` |
| dt | STRING | 分区字段 | `2014-12-06` |

### 3.2 dim_item — 商品维度表

**说明**：商品 ↔ 类目映射关系

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| item_id | BIGINT | 商品ID | `312051294` |
| item_category | BIGINT | 所属类目ID | `8270` |

### 3.3 dim_category — 类目维度表

**说明**：去重类目 + 活跃度标签

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| item_category | BIGINT | 类目ID | `8270` |
| activity_label | STRING | 活跃度标签 | `高活跃` / `中活跃` / `低活跃` |

---

## 四、DWS 汇总层

### 4.1 dws_user_day — 用户日粒度行为汇总

**说明**：每个用户每天的行为次数 + 活跃小时分布
**分区**：`dt`

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| user_id | BIGINT | 用户ID | `98047837` |
| pv_cnt | BIGINT | 当日浏览次数 | `45` |
| fav_cnt | BIGINT | 当日收藏次数 | `2` |
| cart_cnt | BIGINT | 当日加购次数 | `3` |
| buy_cnt | BIGINT | 当日购买次数 | `1` |
| active_hours | INT | 当日活跃小时数（去重） | `8` |
| dt | STRING | 分区字段 | `2014-12-06` |

### 4.2 dws_item_day — 商品日粒度指标

**说明**：每个商品每天的指标
**分区**：`dt`

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| item_id | BIGINT | 商品ID | `232431562` |
| pv_cnt | BIGINT | 当日浏览量 | `890` |
| fav_cnt | BIGINT | 当日收藏量 | `12` |
| cart_cnt | BIGINT | 当日加购量 | `35` |
| buy_cnt | BIGINT | 当日购买量 | `8` |
| buy_conversion | DOUBLE | 购买转化率 = buy_cnt / pv_cnt | `0.0090` |
| dt | STRING | 分区字段 | `2014-12-06` |

### 4.3 dws_category_day — 类目日粒度指标

**说明**：每个类目每天的指标（B 写 NL2SQL 最常用的表之一）
**分区**：`dt`

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| item_category | BIGINT | 类目ID | `4245` |
| pv_cnt | BIGINT | 当日浏览量 | `35000` |
| fav_cnt | BIGINT | 当日收藏量 | `420` |
| cart_cnt | BIGINT | 当日加购量 | `1200` |
| buy_cnt | BIGINT | 当日购买量 | `350` |
| uv | BIGINT | 当日独立访客数 | `8500` |
| buy_conversion | DOUBLE | 购买转化率 = buy_uv / uv | `0.0400` |
| dt | STRING | 分区字段 | `2014-12-06` |

### 4.4 dws_platform_day — 全站日粒度汇总

**说明**：全平台每天的汇总指标
**分区**：`dt`

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| total_uv | BIGINT | 全站DAU（日活跃用户数） | `8230` |
| total_pv | BIGINT | 全站总浏览量 | `385000` |
| total_fav | BIGINT | 全站总收藏量 | `7800` |
| total_cart | BIGINT | 全站总加购量 | `11200` |
| total_buy | BIGINT | 全站总购买量（订单量） | `3900` |
| buy_conversion | DOUBLE | 全站购买转化率 = buy_uv / total_uv | `0.3767` |
| dt | STRING | 分区字段 | `2014-12-06` |

---

## 五、ADS 应用层

> **这一层的表直接支撑 C 的 REST API，D 的大屏图表数据来源即此处。**

### 5.1 ads_daily_kpi — 每日 KPI 汇总

**API**：`GET /api/kpi/cards`（F3.1 KPI指标卡片，含环比变化率）
**分区**：`dt`

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| dau | BIGINT | DAU | `8230` |
| dau_change | DOUBLE | DAU环比变化率 | `0.0160`（+1.6%）|
| total_pv | BIGINT | 全站总PV | `385000` |
| pv_change | DOUBLE | PV环比变化率 | `-0.0200`（-2%）|
| total_orders | BIGINT | 订单量 | `3900` |
| orders_change | DOUBLE | 订单量环比变化率 | `0.0300` |
| buy_conversion | DOUBLE | 全站购买转化率 | `0.3767` |
| conversion_change | DOUBLE | 转化率环比变化 | `0.0050` |
| avg_pv | DOUBLE | 人均PV | `46.78` |
| avg_pv_change | DOUBLE | 人均PV环比变化率 | `-0.0100` |
| dt | STRING | 分区字段 | `2014-12-18` |

### 5.2 ads_funnel — 转化漏斗

**API**：`GET /api/funnel`
**分区**：`dt`

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| item_category | BIGINT | 类目ID（NULL=全站汇总） | `NULL` 或 `4245` |
| level_name | STRING | 层级名称 | `全站` 或类目ID字符串 |
| pv_users | BIGINT | 浏览用户数 | `8230` |
| fav_users | BIGINT | 收藏用户数 | `3200` |
| cart_users | BIGINT | 加购用户数 | `4500` |
| buy_users | BIGINT | 购买用户数 | `3100` |
| pv_to_fav_rate | DOUBLE | 浏览→收藏转化率 | `0.3888` |
| fav_to_cart_rate | DOUBLE | 收藏→加购转化率 | `1.4063`（可能>1，加购不一定先收藏）|
| cart_to_buy_rate | DOUBLE | 加购→购买转化率 | `0.6889` |
| pv_to_buy_rate | DOUBLE | 浏览→购买整体转化率 | `0.3767` |
| dt | STRING | 分区字段 | `2014-12-18` |

### 5.3 ads_category_topn — 类目 TopN 排行

**API**：`GET /api/top/items?limit=10&sort_by=pv`
**分区**：`dt`

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| item_category | BIGINT | 类目ID | `4245` |
| pv_cnt | BIGINT | 浏览量 | `35000` |
| buy_cnt | BIGINT | 购买量 | `350` |
| uv | BIGINT | 独立访客 | `8500` |
| buy_conversion | DOUBLE | 购买转化率 | `0.0400` |
| pv_rank | INT | PV热度排名 | `1` |
| buy_rank | INT | 购买热度排名 | `3` |
| dt | STRING | 分区字段 | `2014-12-18` |

### 5.4 ads_user_rfm — 用户 RFM 分层

**API**：`GET /api/rfm/dist`
**分区**：`dt`（统计截止日）
**评分方法**：三分位数分箱（NTILE(3)），对齐 B 的 `rfm_model.py`

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| user_id | BIGINT | 用户ID | `98047837` |
| r_value | INT | R值：距截止日天数 | `2` |
| f_value | INT | F值：购买总次数 | `8` |
| m_value | INT | M值：购买涉及去重商品数 | `5` |
| r_score | INT | R得分（NTILE3，R越小分越高：3=最近活跃, 1=久未活跃） | `3` |
| f_score | INT | F得分（NTILE3，F越大分越高：3=高频, 1=低频） | `3` |
| m_score | INT | M得分（NTILE3，M越大分越高：3=广泛, 1=单一） | `2` |
| rfm_group | STRING | RFM 组合编码（3位数字） | `332` |
| rfm_label_cn | STRING | RFM 分层标签（9类，对齐 B） | `重要发展用户` |
| dt | STRING | 分区字段（统计截止日） | `2014-12-18` |

**RFM 9类标签对照**（评分均采用 NTILE(3) 三分位，取值 1/2/3，F=0 用户单独处理）：

| rfm_label_cn | R得分 | F得分 | M得分 | 说明 |
|-------------|-------|-------|-------|------|
| **浏览型用户** | — | F=0 | — | 无购买行为，仅浏览 |
| **重要价值用户** | 3（高） | 3（高） | 3（高） | 最近活跃 + 高频 + 广泛，核心用户 |
| **重要发展用户** | 3（高） | 3（高） | 1-2（低） | 最近活跃 + 高频但购买集中，有拓展潜力 |
| **重要保持用户** | 3（高） | 1-2（低） | 3（高） | 最近活跃 + 低频但买得广，需保持 |
| **新锐潜力用户** | 3（高） | 1-2（低） | 1-2（低） | 最近活跃但低频且集中，有转化潜力 |
| **重要挽留用户** | 1-2（低） | 3（高） | 3（高） | 久未活跃但历史高价值，需召回 |
| **一般价值用户** | 1-2（低） | 3（高） | 1-2（低） | 久未活跃，历史高频但集中 |
| **一般发展用户** | 1-2（低） | 1-2（低） | 3（高） | 久未活跃 + 低频，但买得广 |
| **低价值用户** | 1-2（低） | 1-2（低） | 1-2（低） | 三项都低，流失用户 |

### 5.5 ads_user_recommend — 用户个性化推荐

**API**：`GET /api/recommend?user_id=`
**来源**：B 的 `recommender.py`（Item-CF 协同过滤）产出 CSV → HDFS → Hive
**分区**：`dt`（统计截止日）

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| user_id | BIGINT | 用户ID | `4913` |
| item_id | BIGINT | 推荐商品ID | `106533518` |
| score | DOUBLE | 推荐分数（余弦相似度） | `0.8165` |
| reason | STRING | 推荐理由 | `与您购买过的商品361346418偏好相似（相似度0.82）` |
| dt | STRING | 分区字段 | `2014-12-18` |

> ⚠️ 此表依赖 B 先运行 `python analysis/recommender.py`，产出 CSV 后导入 Hive。B 未跑时 C 自动降级为全站热销排行。

---

## 六、分区与查询注意事项

### 6.1 分区策略

- **有分区的表**（按 `dt` 分区，格式 `YYYY-MM-DD`）：
  `ods_user_behavior`, `dwd_user_behavior`, `dws_user_day`, `dws_item_day`, `dws_category_day`, `dws_platform_day`, `ads_daily_kpi`, `ads_funnel`, `ads_category_topn`, `ads_user_rfm`, `ads_user_recommend`

- **无分区的表**（维度表，全量）：
  `ods_item_info`, `dim_item`, `dim_category`

### 6.2 查询示例

```sql
-- KPI 指标卡（C 的 /api/kpi/cards 用）
SELECT * FROM ads_daily_kpi WHERE dt = '2014-12-18';

-- 活跃趋势（C 的 /api/trend/active 用）
SELECT dt, total_uv AS dau, total_pv AS pv, total_buy AS orders
FROM dws_platform_day
WHERE dt BETWEEN '2014-12-12' AND '2014-12-18'
ORDER BY dt;

-- 类目 TopN（C 的 /api/top/items 用）
SELECT item_category, pv_cnt, buy_cnt, uv, buy_conversion
FROM ads_category_topn
WHERE dt = '2014-12-18'
ORDER BY pv_cnt DESC
LIMIT 10;

-- 漏斗（C 的 /api/funnel 用）
SELECT * FROM ads_funnel
WHERE dt = '2014-12-18' AND item_category IS NULL;

-- RFM 分布（C 的 /api/rfm/dist 用）
SELECT rfm_label_cn, COUNT(*) AS cnt
FROM ads_user_rfm
WHERE dt = '2014-12-18'
GROUP BY rfm_label_cn
ORDER BY cnt DESC;

-- 个性化推荐（C 的 /api/recommend 用）
SELECT item_id, score, reason
FROM ads_user_recommend
WHERE dt = '2014-12-18' AND user_id = 4913
ORDER BY score DESC
LIMIT 10;

-- ❌ 不带分区全表扫描（会很慢，不要这样写）
SELECT * FROM dws_platform_day;
```

### 6.3 表关联关系

```
ods_user_behavior ──LEFT JOIN── ods_item_info (item_id)
        │                              │
        └──────────┬───────────────────┘
                   ↓
         dwd_user_behavior
              │
    ┌─────────┼─────────┐
    ↓         ↓         ↓
dws_user  dws_item  dws_category  dws_platform
  _day      _day       _day           _day
    │         │          │              │
    └─────────┴──────────┴──────────────┘
                   ↓
    ads_daily_kpi / ads_funnel / ads_category_topn / ads_user_rfm / ads_user_recommend
```

```
dim_item (item_id → item_category)
dim_category (item_category → activity_label)
```

---

## 七、数据时间范围

| 项目 | 说明 |
|------|------|
| 数据起止日期 | 2014-11-18 ~ 2014-12-18（共31天） |
| 数据截止日 | 2014-12-18（RFM 统计截止日） |
| 时间粒度 | 小时级（behavior_hour: 0-23） |
| 最早分区 | `dt='2014-11-18'` |
| 最晚分区 | `dt='2014-12-18'` |
