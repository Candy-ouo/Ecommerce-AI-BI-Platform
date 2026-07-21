# 后端 API 接口文档（角色 C 提供）

> 本文档是 **C → D（前端）** 和 **C → B（AI 模块 tools.py）** 的接口契约。
> 数据目前为 **Mock 模式**（`USE_REAL_DATA=false`），前端可直接联调；A 的 Hive 表就绪后切真实数据，接口形状不变。
> 所有 REST 接口统一返回 **`{code, message, data}`** 包装（见下方「统一响应结构」）。

- **Base URL（开发）**：`http://localhost:5000`
- **CORS**：已开启，前端跨域可直接调

### 统一响应结构

所有 REST 接口统一返回如下结构（`data` 内为各接口业务字段）：

```json
{ "code": 0, "message": "success", "data": { } }
```

| 字段 | 说明 |
|------|------|
| `code` | `0` 成功；非 `0` 为业务/系统错误（与 HTTP 状态码可并存，如 500 / 404） |
| `message` | 提示信息，`"success"` 或错误描述文本 |
| `data` | 业务数据对象（各接口具体字段见下文；失败时为 `null`） |

> 失败时示例：`{ "code": 500, "message": "no data", "data": null }`

---

## 1. GET /api/kpi/cards
核心 KPI 指标卡。

**响应**（`data` 内）
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "date": "2014-12-18",
    "dau": 12345,
    "dau_change": -0.03,
    "orders": 8900,
    "orders_change": 0.061,
    "conversion_rate": 0.0382,
    "conversion_change": 0.005,
    "avg_pv": 8.5,
    "avg_pv_change": 0.024
  }
}
```
| 字段 | 说明 |
|------|------|
| date | 数据日期 `YYYY-MM-DD` |
| dau | 日活跃用户数 |
| dau_change | DAU 环比（`-0.03` = 降 3%） |
| orders | 订单量（购买行为数） |
| orders_change | 订单量环比 |
| conversion_rate | 全站购买转化率（购买用户数 / DAU） |
| conversion_change | 转化率环比 |
| avg_pv | 人均 PV |
| avg_pv_change | 人均 PV 环比 |
| ai_insight | AI 分析洞察（仅 LLM 可用时返回，约 150-300 字中文分析；无 LLM key 时不存在） |

---

## 2. GET /api/trend/active?days=7[&category=4245]

近 N 日活跃趋势（折线图）。支持全站和类目维度。

**参数**：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| days | int | 7 | 返回最近 N 天 |
| category | string | (空) | 类目ID；为空/`"all"` → 全站汇总；传类目ID → 该类目维度趋势 |

**响应**（`data` 内）
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "dates": ["07-14", "07-15", "07-16", "07-17", "07-18", "07-19", "07-20"],
    "dau":   [12000, 12500, 11800, 13100, 12900, 13400, 13050],
    "pv":    [96000, 99000, 94000, 102000, 100000, 105000, 103000],
    "orders": [3800, 3900, 3700, 4100, 4000, 4200, 4100]
  }
}
```
- `orders` 为每日订单量，前端 charts.js 渲染折线图第三条折线
- `dates` 为 `MM-DD` 格式，**升序**（直接喂 ECharts x 轴）
- `dau` / `pv` 与 `dates` 一一对应

---

## 3. GET /api/top/items?limit=10&sort_by=pv
商品热度 TopN（柱状图）。

**参数**：
- `limit`（int，默认 10）
- `sort_by`（枚举：`pv` | `fav` | `buy`，默认 `pv`）

**响应**（`data` 内）
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {"item_id": "item_1", "name": "商品 A", "pv": 9000, "fav": 3000, "buy": 1500},
      {"item_id": "item_2", "name": "商品 B", "pv": 8900, "fav": 2920, "buy": 1480}
    ]
  }
}
```
- 按 `sort_by` **降序**排列
- `item_id` 为字符串；`name` 为前端展示名（真实数据为脱敏 ID，降级为 `"商品 {item_id}"`）

---

## 4. GET /api/funnel
全站转化漏斗（漏斗图）。

**响应**（`data` 内）
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "pv": 100000,
    "fav": 35000,
    "cart": 20000,
    "buy": 8000,
    "pv_to_fav_rate": 0.35,
    "fav_to_cart_rate": 0.5714,
    "cart_to_buy_rate": 0.4,
    "pv_to_buy_rate": 0.08
  }
}
```
- 顺序即漏斗层级：浏览 → 收藏 → 加购 → 购买
- `*_rate` 为各级转化率（分母为 0 时取 `0`）

---

## 5. GET /api/rfm/dist
RFM 9 类用户占比（饼图，含"浏览型用户"）。

**响应**（`data` 内）
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "labels": ["重要价值用户", "重要发展用户", "重要保持用户", "重要挽留用户",
               "一般价值用户", "一般发展用户", "新锐潜力用户", "低价值用户",
               "浏览型用户"],
    "counts": [1200, 800, 600, 400, 1500, 900, 550, 480, 720]
  }
}
```
- `labels` 与 `counts` 一一对应

---

## 6. GET /api/recommend?user_id=123&limit=10
个性化推荐列表。

**参数**：
- `user_id`（int，**必填**）
- `limit`（int，默认 10）

**响应**（`data` 内）
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_id": 98047837,
    "items": [
      {"item_id": "rec_item_1", "name": "商品 232431562", "score": 0.95, "reason": "协同过滤"},
      {"item_id": "rec_item_2", "name": "商品 312051294", "score": 0.90, "reason": "协同过滤"}
    ]
  }
}
```
- `data.user_id`：请求的用户ID，供前端 `#recommend-user` 展示
- `data.items[].name`：商品名称（真实数据为脱敏 ID，降级为 "商品 {item_id}"）

---

## 7. POST /api/chat （SSE 流式）
AI 对话（自然语言问数 → 文本 + 图表）。

**请求体**
```json
{ "message": "上周销量最高的商品？" }
```
> 也兼容 `{ "question": "..." }`（D 前端 `ai_chat.js` 实际使用此字段名）

**响应**：`text/event-stream`，每个事件一行（`data:` 后跟 JSON）：

```
data: {"type":"text","content":"好的，我来帮你查询..."}

data: {"type":"chart","chartType":"bar","data":{"categories":["浏览","收藏","加购","购买"],"values":[100000,35000,20000,8000]}}

data: {"type":"done"}
```
| type | 含义 |
|------|------|
| `text` | 文本分片，前端逐字追加到聊天气泡 |
| `chart` | 图表数据，结构见下 |
| `done` | 流结束 | `done` 事件附带 `session_id`：`{"type":"done","session_id":"a1b2c3d4"}` |

**多轮对话**：
- 请求体可传 `session_id`（可选）；首次请求不传则后端自动生成，在 `done` 事件中返回
- 后续请求携带同一 `session_id` 即可复用对话历史（最多 10 轮），后端将上下文注入 NL2SQL 提示

**`chart` 数据结构**（对齐前端 `ai_chat.js` 的 `buildChartOption`）：

| chartType | `data` 字段 |
|-----------|-------------|
| `bar` / `line` | `categories: string[]`（x 轴类目）、`values: number[]`（y 轴数值） |
| `pie` | `labels: string[]`、`counts: number[]` |
| 任意 | 可选 `option`：完整 ECharts option，前端优先直传渲染 |

> 真实模式（`USE_REAL_DATA=true`）已接入 B 的 NL2SQL：`generate_sql → query(Hive) → explain_result`，非数据问题会安全拒绝（`UNABLE_TO_ANSWER`）。Mock 模式仅回显文本 + `done`，不含 chart 事件（前端 `mockSend` 自行生成示例图）。

---

## 给 B 的 tools.py 调用提示
B 在 `ai/agent/tools.py` 中通过 HTTP 调用以上接口获取大屏数据，可用 `requests`：
```python
import requests
BASE = "http://localhost:5000"
def get_kpi():      return requests.get(f"{BASE}/api/kpi/cards").json()["data"]
def get_trend():    return requests.get(f"{BASE}/api/trend/active?days=7").json()["data"]
def get_top():      return requests.get(f"{BASE}/api/top/items?limit=10").json()["data"]
def get_funnel():   return requests.get(f"{BASE}/api/funnel").json()["data"]
def get_rfm():      return requests.get(f"{BASE}/api/rfm/dist").json()["data"]
```
> 注意所有接口都包了 `{code, message, data}`，调用方取 `.json()["data"]` 拿业务数据。

（推荐接口需带 `user_id`；chat 为 SSE，Agent 一般不直接调，由前端直连。）

---

## 8. GET /api/report/latest + /api/report/history + /api/report/stream

AI 晨报接口。

### 8.1 GET /api/report/latest
最新一期晨报。

**响应**（`data` 内）
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "date": "2014-12-18",
    "content": "今日 DAU 12,345（环比 +3.2%）...",
    "anomalies": ["数码品类转化率下降 12%"]
  }
}
```

### 8.2 GET /api/report/history?days=7
最近 N 天晨报列表（按日期降序）。

### 8.3 GET /api/report/stream （SSE 流式）
晨报实时推送。大屏建立长连接后，scheduler 每日 8:00 生成新晨报时自动推送，无需轮询。

**响应**：`text/event-stream`，每 30 秒心跳保活：
```
data: {"type":"ping"}

data: {"type":"report","date":"2014-12-18","content":"今日...","anomalies":["..."]}
```

---

## 9. API 鉴权

所有 `/api/*` 接口支持 Bearer Token 鉴权。

- **未配置** `API_TOKEN`（`.env` 中为空）：鉴权关闭，所有请求放行（开发/演示模式）
- **已配置** `API_TOKEN=your-secret`：请求需携带 `Authorization: Bearer your-secret` 头，否则返回 `401`（缺头）或 `403`（token 错误）

> `/health` 端点不受鉴权保护。

```bash
# 鉴权请求示例
curl -H "Authorization: Bearer your-secret" http://localhost:5000/api/kpi/cards
```
