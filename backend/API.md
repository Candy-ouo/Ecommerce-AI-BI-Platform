# 后端 API 接口文档（角色 C 提供）

> 本文档是 **C → D（前端）** 和 **C → B（AI 模块 tools.py）** 的接口契约。
> 数据目前为 **Mock 模式**（`USE_REAL_DATA=false`），前端可直接联调；A 的 Hive 表就绪后切真实数据，接口形状不变。

- **Base URL（开发）**：`http://localhost:5000`
- **CORS**：已开启，前端跨域可直接调
- **错误格式**：`{"error": "..."}` 并带 HTTP 状态码（如 500 / 404）

---

## 1. GET /api/kpi/cards
核心 KPI 指标卡。

**响应**
```json
{
  "dau": 12345,
  "dau_change": -0.03,
  "orders": 8900,
  "conversion_rate": 0.12,
  "avg_pv": 8.5
}
```
| 字段 | 说明 |
|------|------|
| dau | 日活跃用户数 |
| dau_change | DAU 环比（`-0.03` = 降 3%） |
| orders | 订单量（购买行为数） |
| conversion_rate | 全站购买转化率（购买用户数 / DAU） |
| avg_pv | 人均 PV |

---

## 2. GET /api/trend/active?days=7
近 N 日活跃趋势（折线图）。

**参数**：`days`（int，默认 7）

**响应**
```json
{
  "dates": ["07-14", "07-15", "07-16", "07-17", "07-18", "07-19", "07-20"],
  "dau":   [12000, 12500, 11800, 13100, 12900, 13400, 13050],
  "pv":    [96000, 99000, 94000, 102000, 100000, 105000, 103000]
}
```
- `dates` 为 `MM-DD` 格式，**升序**（直接喂 ECharts x 轴）
- `dau` / `pv` 与 `dates` 一一对应

---

## 3. GET /api/top/items?limit=10&sort_by=pv
商品热度 TopN（柱状图）。

**参数**：
- `limit`（int，默认 10）
- `sort_by`（枚举：`pv` | `fav` | `buy`，默认 `pv`）

**响应**
```json
{
  "items": [
    {"item_id": "item_1", "pv": 9000, "fav": 3000, "buy": 1500},
    {"item_id": "item_2", "pv": 8900, "fav": 2920, "buy": 1480}
  ]
}
```
- 按 `sort_by` **降序**排列
- `item_id` 为字符串

---

## 4. GET /api/funnel
全站转化漏斗（漏斗图）。

**响应**
```json
{
  "pv": 100000,
  "fav": 35000,
  "cart": 20000,
  "buy": 8000
}
```
- 顺序即漏斗层级：浏览 → 收藏 → 加购 → 购买

---

## 5. GET /api/rfm/dist
RFM 8 类用户占比（饼图）。

**响应**
```json
{
  "labels": ["重要价值", "重要发展", "重要保持", "重要挽留",
             "一般价值", "一般发展", "一般保持", "一般挽留"],
  "counts": [1200, 800, 600, 400, 1500, 900, 700, 500]
}
```
- `labels` 与 `counts` 一一对应

---

## 6. GET /api/recommend?user_id=123&limit=10
个性化推荐列表。

**参数**：
- `user_id`（int，**必填**）
- `limit`（int，默认 10）

**响应**
```json
{
  "items": [
    {"item_id": "rec_item_1", "score": 0.95, "reason": "协同过滤"},
    {"item_id": "rec_item_2", "score": 0.90, "reason": "协同过滤"}
  ]
}
```

---

## 7. POST /api/chat （SSE 流式）
AI 对话（自然语言问数 → 文本 + 图表）。

**请求体**
```json
{ "message": "上周销量最高的商品？" }
```

**响应**：`text/event-stream`，每个事件一行：
```
data: {"type":"text","content":"好的，我来帮你查询..."}

data: {"type":"chart","chartType":"bar","data":{"x":["浏览","收藏","加购","购买"],"y":[100000,35000,20000,8000]}}

data: {"type":"done"}
```
| type | 含义 |
|------|------|
| `text` | 文本分片，前端逐字追加到聊天气泡 |
| `chart` | 图表数据，`chartType` 为 `bar`/`line`/`pie` 等，`data` 为图表数据 |
| `done` | 流结束 |

> 当前为 Mock 流式；B 的 AI 模块（NL2SQL / Agent / 解读）接入后为真实分析。

---

## 给 B 的 tools.py 调用提示
B 在 `ai/agent/tools.py` 中通过 HTTP 调用以上接口获取大屏数据，可用 `requests`：
```python
import requests
BASE = "http://localhost:5000"
def get_kpi():      return requests.get(f"{BASE}/api/kpi/cards").json()
def get_trend():    return requests.get(f"{BASE}/api/trend/active?days=7").json()
def get_top():      return requests.get(f"{BASE}/api/top/items?limit=10").json()
def get_funnel():   return requests.get(f"{BASE}/api/funnel").json()
def get_rfm():      return requests.get(f"{BASE}/api/rfm/dist").json()
```
（推荐接口需带 `user_id`；chat 为 SSE，Agent 一般不直接调，由前端直连。）
