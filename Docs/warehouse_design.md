# A模块交付文档 —— 数据仓库四层架构

> **负责人：A**  
> **分支：feature/a-warehouse**  
> **最后更新：2026-07-21**

---

## 一、文件清单

```
warehouse/
├── 01_ods_ddl.sql              ✅ ODS 贴源层：建库 + 建表 + 加载数据（2 张表）
├── 02_dwd_etl.sql              ✅ DWD 明细层：Join + 去重 + 标准化 + 维度表（3 张表）
├── 03_dws_agg.sql              ✅ DWS 汇总层：日粒度聚合（4 张表）
└── 04_ads_app.sql              ✅ ADS 应用层：API 即查即用指标（4 张表）

docs/
└── schema.md                   ✅ 全部 13 张表的字段字典（B 写 NL2SQL + C 写 API 的核心依赖）
```

---

## 二、数据仓库分层架构

```
ADS 应用层  ←── C 的 REST API 直接查这层（4 张表）
  ↑
DWS 汇总层  ←── 日粒度聚合，C 复杂查询可查这层（4 张表）
  ↑
DWD 明细层  ←── 两表 Join、去重、标准化后的干净明细（3 张表）
  ↑
ODS 贴源层  ←── E 清洗后直接导入（2 张表）
```

**共 13 张表**，全部存储在 Hive（HDFS + PostgreSQL Metastore），重启不丢失。

---

## 三、每层详解

---

### 3.1 ODS 贴源层（`01_ods_ddl.sql`）

| 表名 | 说明 | 数据量 | 分区 |
|------|------|--------|------|
| `ods_user_behavior` | 用户行为表（E 清洗后导入） | **12,256,906** 行 | `dt` |
| `ods_item_info` | 商品信息表（E 清洗去重后导入） | **310,582** 行 | 无 |

**存储格式**：TEXTFILE（原始 CSV 导入，不做压缩）

**E → A 数据契约**：

| 字段 | 说明 |
|------|------|
| `behavior_type_cn` | E 清洗时新增：1→浏览 2→收藏 3→加购 4→购买 |
| `behavior_date` | E 从原始 `time` 列拆分：`2014-12-06` |
| `behavior_hour` | E 从原始 `time` 列拆分：`2`（0-23） |

---

### 3.2 DWD 明细层（`02_dwd_etl.sql`）

| 表名 | 说明 | 数据量 | 分区 |
|------|------|--------|------|
| `dwd_user_behavior` | 用户行为 + 商品信息两表 Join，去重 | **6,213,379** 行 | `dt` |
| `dim_item` | 商品 ↔ 类目映射 | **310,582** 行 | 无 |
| `dim_category` | 去重类目 + 活跃度标签 | **8,916** 行 | 无 |

**关键逻辑**：
- `ods_user_behavior` LEFT JOIN `ods_item_info` 补全商品 geohash
- `ROW_NUMBER()` 按 `(user_id, item_id, behavior_type, behavior_date, behavior_hour)` 去重
- `dim_category` 按类目下活跃用户数打标签：≥1000 高活跃 / ≥100 中活跃 / 其余低活跃

---

### 3.3 DWS 汇总层（`03_dws_agg.sql`）

| 表名 | 说明 | 粒度 | 分区 |
|------|------|------|------|
| `dws_user_day` | 用户日粒度：PV/收藏/加购/购买次数 + 活跃小时 | 每天每用户 | `dt` |
| `dws_item_day` | 商品日粒度：PV/收藏/加购/购买 + 购买转化率 | 每天每商品 | `dt` |
| `dws_category_day` | 类目日粒度：PV/收藏/加购/购买/UV/转化率 | 每天每类目 | `dt` |
| `dws_platform_day` | 全站日粒度：总UV/PV/收藏/加购/购买/转化率 | 每天 | `dt` |

**B 写 NL2SQL 最常用的表**：`dws_category_day`（类目分析）、`dws_platform_day`（趋势）、`dws_item_day`（商品排行）

---

### 3.4 ADS 应用层（`04_ads_app.sql`）

| 表名 | 对应 API | 说明 |
|------|----------|------|
| `ads_daily_kpi` | `GET /api/kpi/cards` | DAU/PV/订单量/转化率/人均PV + 全部环比变化率 |
| `ads_funnel` | `GET /api/funnel` | 全站 + 各类目漏斗：浏览→收藏→加购→购买各环节人数与转化率 |
| `ads_category_topn` | `GET /api/top/items` | 类目 PV/购买热度排行（含 pv_rank、buy_rank） |
| `ads_user_rfm` | `GET /api/rfm/dist` | 用户 R/F/M 原始值 + NTILE(3)三分位评分 + 9类分层标签 |

**RFM 9 类标签**（NTILE(3)三分位评分，F=0 用户单独处理，对齐 B 的 `rfm_model.py`）：浏览型用户 / 重要价值用户 / 重要发展用户 / 重要保持用户 / 新锐潜力用户 / 重要挽留用户 / 一般价值用户 / 一般发展用户 / 低价值用户

---

## 四、数据验证结果

在 Docker Hive 环境（`bde2020/hive:2.3.2`）上全部执行通过：

| 表 | 行数 | 状态 |
|---|------|------|
| `ods_user_behavior` | 12,256,906 | ✅ |
| `ods_item_info` | 310,582 | ✅ |
| `dwd_user_behavior` | 6,213,379 | ✅ |
| `dim_item` | 310,582 | ✅ |
| `dim_category` | 8,916 | ✅ |
| `dws_user_day` ~ `ads_user_rfm` | 全部执行成功 | ✅ |

---

## 五、执行说明

### 前置条件

1. Docker 环境：Hive Server2 + HDFS + YARN 已启动
2. E 的清洗后 CSV 已上传 HDFS `/user/data/`

### 一键执行

```bash
# 1. 上传清洗后的 CSV 到 HDFS
docker cp data/processed/user_behavior_clean.csv tier4_stu_namenode:/tmp/
docker cp data/processed/item_info_clean.csv tier4_stu_namenode:/tmp/
docker exec tier4_stu_namenode hdfs dfs -mkdir -p /user/data
docker exec tier4_stu_namenode hdfs dfs -put /tmp/user_behavior_clean.csv /user/data/
docker exec tier4_stu_namenode hdfs dfs -put /tmp/item_info_clean.csv /user/data/

# 2. 拷 SQL 进容器并执行
docker cp warehouse/*.sql tier4_stu_hiveserver2:/tmp/
docker exec tier4_stu_hiveserver2 hive -f /tmp/01_ods_ddl.sql
docker exec tier4_stu_hiveserver2 hive -f /tmp/02_dwd_etl.sql
docker exec tier4_stu_hiveserver2 hive -f /tmp/03_dws_agg.sql
docker exec tier4_stu_hiveserver2 hive -f /tmp/04_ads_app.sql
```

---

## 六、B / C 集成指南

### B 怎么用（NL2SQL）

B 的 `schema_context.py` 读取 `docs/schema.md`，生成 Prompt 上下文。所有 13 张表的结构已在 schema.md 中完整定义。

### C 怎么用（API）

C 的 `hive_client.py` 连接 Hive Server2（`localhost:10000`），查询示例：

```python
from pyhive import hive
conn = hive.Connection(host='localhost', port=10000, database='ecommerce_bi')

# KPI 卡片
cursor = conn.cursor()
cursor.execute('SELECT * FROM ads_daily_kpi WHERE dt = "2014-12-18"')

# 活跃趋势
cursor.execute('SELECT dt, total_uv, total_pv, total_buy FROM dws_platform_day WHERE dt BETWEEN "2014-12-12" AND "2014-12-18" ORDER BY dt')

# 漏斗
cursor.execute('SELECT * FROM ads_funnel WHERE dt = "2014-12-18" AND item_category IS NULL')

# 类目 TopN
cursor.execute('SELECT * FROM ads_category_topn WHERE dt = "2014-12-18" ORDER BY pv_rank LIMIT 10')

# RFM 分布
cursor.execute('SELECT rfm_label_cn, COUNT(*) FROM ads_user_rfm WHERE dt = "2014-12-18" GROUP BY rfm_label_cn')
```

---

## 七、schema.md 查询速查

| 想知道 | 查这张表 | 关键列 |
|--------|---------|--------|
| 全站 KPI + 环比 | `ads_daily_kpi` | `dau`, `total_orders`, `buy_conversion`, `avg_pv`, 各 `_change` |
| 近 7 天 DAU/PV 趋势 | `dws_platform_day` | `total_uv`, `total_pv`, `total_buy`, `dt` |
| 类目热度 TopN | `ads_category_topn` | `item_category`, `pv_cnt`, `buy_cnt`, `pv_rank` |
| 全站转化漏斗 | `ads_funnel` | `pv_users`→`fav_users`→`cart_users`→`buy_users` |
| RFM 用户分群 | `ads_user_rfm` | `rfm_label_cn` → `GROUP BY + COUNT` |
| 某商品每天走势 | `dws_item_day` | `item_id`, `pv_cnt`, `buy_cnt`, `dt` |
| 类目转化率排名 | `dws_category_day` | `item_category`, `buy_conversion`, `dt` |
| 用户行为明细 | `dwd_user_behavior` | `user_id`, `item_id`, `behavior_type_cn`, `behavior_date` |
| 类目活跃度 | `dim_category` | `item_category`, `activity_label` |

---

## 八、技术要点

| 项目 | 说明 |
|------|------|
| 存储格式 | ODS: TEXTFILE / DWD/ADS: **ORC**（Hive 原生列存，高压缩比 + 快查询） |
| 分区策略 | 10 张日表按 `dt` (YYYY-MM-DD) 分区，查询必带 WHERE dt= |
| 动态分区 | 已设置 `hive.exec.dynamic.partition.mode=nonstrict` |
| 内存配置 | Map 1GB / Reduce 1GB / JVM 800MB（已内置在 SQL 文件中） |
| 数据持久化 | HDFS（namenode 命名卷）+ PostgreSQL Metastore，Docker 重启不丢 |
| 时间范围 | 2014-11-18 ~ 2014-12-18（31 天），RFM 截止日 2014-12-18 |
