# 数据集说明

## 数据来源

**Tianchi Mobile Recommendation**（阿里天池移动推荐算法竞赛数据集）

- 竞赛页面：https://tianchi.aliyun.com/dataset/dataDetail?dataId=46
- 下载后放置路径：`data/tianchi_mobile_recommend_train_user.csv` 和 `data/tianchi_mobile_recommend_train_item.csv`

## 数据文件

| 文件名 | 大小 | 行数 | 说明 |
|--------|------|------|------|
| `tianchi_mobile_recommend_train_user.csv` | ~400MB | 12,256,906 | 用户行为流水表 |
| `tianchi_mobile_recommend_train_item.csv` | ~6MB | 480,723 | 商品信息表 |

## 字段字典

### 用户行为表 (tianchi_mobile_recommend_train_user.csv)

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | INT | 用户ID（共10,000人） |
| item_id | INT | 商品ID |
| behavior_type | INT | 1=浏览, 2=收藏, 3=加购, 4=购买 |
| user_geohash | STRING | 用户地理位置哈希（68%为空） |
| item_category | INT | 商品类目ID |
| time | STRING | 行为时间，格式 `YYYY-MM-DD HH`，范围 2014-11-18 ~ 2014-12-18 |

### 商品信息表 (tianchi_mobile_recommend_train_item.csv)

| 字段 | 类型 | 说明 |
|------|------|------|
| item_id | INT | 商品ID（非唯一，48万行仅31万去重商品） |
| item_geohash | STRING | 商品地理位置哈希（64%为空） |
| item_category | INT | 商品类目ID（共991个类目） |

## 数据分布概览

| 行为类型 | 数量 | 占比 |
|----------|------|------|
| 浏览 (1) | 11,550,581 | 94.2% |
| 加购 (3) | 343,564 | 2.8% |
| 收藏 (2) | 242,556 | 2.0% |
| 购买 (4) | 120,205 | 1.0% |

## 清洗规则

1. `time` 字段拆分为 `behavior_date` (YYYY-MM-DD) + `behavior_hour` (0-23)
2. `behavior_type` 数字映射为中文：1→浏览, 2→收藏, 3→加购, 4→购买
3. 一期默认丢弃 `user_geohash` 和 `item_geohash` 列（有效值不足40%）
4. 商品信息表按 `item_id` 去重（48万行→31万行）
5. 过滤异常时间戳与异常行为类型值

## 开发样本

`data/sample/sample_10k.csv` — 从用户行为表随机抽取10,000条 + 关联商品信息表，供开发调试使用。
