# C 模块交付说明 —— 后端 API + 数据接入

负责人：C
分支：`feature/c-backend`
最后更新：2026-07-21（P3：KPI环比补全 + RFM动态分区 + 频率限制 + 连接池 + 日志轮转 + SSE清理 + 饼图推断 + 参数校验）

---

## 一、文件清单（backend/）

```
backend/
├── app.py                 ← Flask 入口，注册所有 Blueprint，CORS，启动 scheduler，日志轮转
├── config.py              ← 统一配置（Hive/MySQL/LLM/Flask/数据开关）
├── scheduler.py           ← APScheduler 定时任务（每天 8:00 触发晨报生成 + 钉钉推送 + SSE通知）
├── api/
│   ├── __init__.py        ← Blueprint 注册（8 个模块）
│   ├── _response.py       ← 统一响应包装 {code, message, data}（对齐 D 前端 api.js）
│   ├── _auth.py           ← Bearer Token 鉴权装饰器（可选开启）
│   ├── kpi.py             ← GET  /api/kpi/cards（含4项环比 + AI洞察）
│   ├── trend.py           ← GET  /api/trend/active（参数校验：days/category）
│   ├── top.py             ← GET  /api/top/items（sort_by白名单防注入）
│   ├── funnel.py          ← GET  /api/funnel（含各级转化率）
│   ├── rfm.py             ← GET  /api/rfm/dist（Mock/Real双模式，动态取最新分区）
│   ├── recommend.py       ← GET  /api/recommend?user_id=（已接真实数据链路）
│   ├── report.py          ← GET  /api/report/latest + /history + /stream（SSE实时推送+断连清理）
│   └── chat.py            ← POST /api/chat（SSE流式，smart_chat混合路由，频率限制，饼图推断）
├── services/
│   ├── hive_client.py     ← pyhive/DuckDB 查询封装
│   ├── db.py              ← MySQL 封装（DBUtils连接池 + 回退普通连接）
│   └── queries.py         ← Hive SQL（字段名已对齐 A 的 schema.md）
├── API.md                 ← 接口详细文档（给 D 联调、B 写 tools.py）
├── requirements.txt       ← 完整依赖清单（含 apscheduler/requests/DBUtils）
├── .env.example           ← 环境变量模板（占位符，不含真实 key）
└── logs/                  ← 日志轮转目录（backend.log, 5MB×3备份）
```
```

当前状态：**全部交付**。11 个接口（9 REST + 2 SSE）+ 1 个健康检查，Mock 模式全部跑通。99 个测试 0 失败。响应格式统一 `{code, message, data}`（对齐 D 前端 `api.js`）。SSE chart 事件支持 pie/line/bar 自动推断（对齐 D 的 `ai_chat.js`）。

### P3 本轮新增（2026-07-21）

| 改进 | 文件 | 说明 |
|------|------|------|
| KPI 环比补全 | `api/kpi.py` | 真实模式补充 orders_change、conversion_change、avg_pv_change |
| RFM 动态分区 | `api/rfm.py` | SELECT MAX(dt) 去硬编码日期 |
| 频率限制 | `api/chat.py` | 每 IP 每分钟最多 10 次，防刷 LLM 费用 |
| 饼图推断 | `api/chat.py` | _df_to_chart 自动识别：行数≤5 → pie |
| 参数校验 | `api/trend.py` | category 非整数返回 400 |
| 连接池 | `services/db.py` | DBUtils PooledDB（最大5连接），未安装自动回退 |
| 日志轮转 | `app.py` | RotatingFileHandler，5MB×3备份 → logs/backend.log |
| SSE 清理 | `scheduler.py` / `api/report.py` | unsubscribe_report 修复订阅者内存泄漏 |
| 依赖补全 | `requirements.txt` | 补充 apscheduler、requests、DBUtils |

---

## 二、给各角色的对接说明

### 2.1 给 D（前端）

> C 的后端 9 个接口已全部跑通（Mock 模式+82测试全过）。文档在 `backend/API.md`。
> **响应格式已统一**：所有 REST 接口返回 `{"code": 0, "message": "success", "data": {...}}`，对齐你 `frontend/js/api.js` 的 `request()` 逻辑。
> **SSE chart 格式**：`{"type":"chart","chartType":"bar","data":{"categories":["A","B"],"values":[1,2]}}`，对齐你 `ai_chat.js` 的 `buildChartOption()`。
> Mock 模式下 chat 不再发 chart 事件（你前端 `mockSend` 自己生成）。
> 本地启动：`cd backend && pip install -r requirements.txt && python app.py`，然后访问 `http://localhost:5000/api/kpi/cards` 等即可联调。

---

### 2.2 给 B（AI）

> 接口端点清单在 `backend/API.md` 末尾（`tools.py` 调用示例已写好）。
> **2026-07-21 更新**：C 已为 B 的 `ai/agent/tools.py` 做好适配 — `_get()` 自动解包 `{code,message,data}` 包装层，Agent 拿到的就是纯业务字段（跟 tools.py 的 docstring 一致）。
> 模型名用 `qwen-plus`（已实测可通）。LLM 配置**统一用 B 的变量名**（B 说了算），在本地 `.env` 里填：

```env
# LLM（阿里云百炼 / 通义千问，OpenAI 兼容格式，变量名与 B 的 llm_client.py 一致）
LLM_PROVIDER=qwen
QWEN_API_KEY=<你自己的百炼 API Key>
QWEN_BASE_URL=https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

> ⚠️ 提交时注意：只提交 `.env.example`（占位符模板），**真实 `.env` 已被 gitignore，勿提交，否则泄露 key**。
> C 的 `config.py` 已对齐 B 的命名（`QWEN_API_KEY` / `QWEN_BASE_URL`），B 的 `llm_client.py` 直接读即可，无需改代码。

---

### 2.3 给 A（数仓）

> A 你好，C 的 `queries.py` 当前按以下假设写 SQL，请确认表名/字段名是否一致
> （不一致告诉我，我改顶部常量即可，不动接口逻辑）：

| 用途 | C 假设表名 | C 假设字段 |
|------|-----------|-----------|
| 日 KPI | `ads_daily_kpi` | dt, dau, total_orders, buy_conversion, avg_pv |
| 全站日 | `dws_platform_day` | dt, total_uv, total_pv |
| 商品日 | `dws_item_day` | dt, item_id, pv_cnt, fav_cnt, buy_cnt |
| 漏斗 | `ads_funnel` | dt, pv_users, fav_users, cart_users, buy_users（转化率列待 D 需要再扩展） |
| RFM | `ads_user_rfm` | dt, user_id, rfm_label_cn, rfm_group, cnt |

> 另外 C 的 `rfm.py` 已改为**直读 Hive ads_user_rfm**（跟 KPI/趋势/漏斗统一，`rfm_label_cn` 字段），
> MySQL 路径已去掉。推荐数据仍查 MySQL 表 `recommends`（B 的 CSV 导入后建此表）。
> 最终以你的 `docs/schema.md` 为准。

---

## 三、从 B 的 AI 设计文档中，C 需注意 / 可复用的点

### 3.1 RFM 数据链路（已改为直读 A 的 Hive，不再走 MySQL）

A 的 `ads_user_rfm`（Hive）用 NTILE(3) 三分位打了 9 类标签（字段 `rfm_label_cn`），
跟 B 的 `rfm_model.py` 算法一致。C 的 `GET /api/rfm/dist` 已改为直读 Hive，
与 KPI/趋势/漏斗接口统一，不再走 B→MySQL→C 绕路。

> A 的 `rfm_label_cn` 为 9 类中文标签。旧 MySQL 路径的 `services/db.py` 中 `get_rfm()` 保留不动（/api/recommend 仍走 MySQL）。
> B 的 `rfm_model.py` 产出 `rfm_result.csv` 仍可用于交叉验证（本文档 3.3 导入 SQL 保留参考）。

### 3.2 推荐结果结构（接真实数据时返回 item_id + score + reason）

B 的 `recommender.py` 产出 `data/recommend_result.csv`（字段 `user_id, item_id, score, reason`），导入 MySQL 后表名为 `recommends`（按 B 的 b_dual_path.md）。
`reason` 为 LLM 生成的推荐理由（按 DEV_PLAN 需求）。
C 的 `GET /api/recommend` 已对齐，返回 `[{item_id, score, reason}]`。

### 3.3 数据导入 MySQL 参考（B 提供）

```sql
-- RFM 结果
LOAD DATA LOCAL INFILE 'data/rfm_result.csv'
INTO TABLE rfm_result
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
IGNORE 1 ROWS;

-- 推荐结果（注意 MySQL 表名为 recommends，不是 recommend_result）
LOAD DATA LOCAL INFILE 'data/recommend_result.csv'
INTO TABLE recommends
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
IGNORE 1 ROWS;
```

### 3.4 `ai/insights.py`（✅ 已接入 kpi/cards）

B 新增了 AI 数据洞察模块：输入 KPI 字典 → LLM 生成三段式中文分析报告（核心指标概览 + 趋势异常 + 运营建议）。

```python
from ai.insights import generate_insights
kpi = {"dau": 8230, "total_orders": 3900, "buy_conversion": 0.377}
report = generate_insights(kpi)  # → 约 200-300 字中文分析
```

> C 已在 `/api/kpi/cards` 接入（惰性导入，字段名映射：`orders→total_orders`、`conversion_rate→buy_conversion`）。
> 无 LLM key 时静默跳过，不影响 KPI 正常返回。返回字段：`data.ai_insight`。

### 3.5 `chat.py` 集成参考（B 第 4 节提供）

B 文档给出了完整的 `/api/chat` 调用链路（含安全拒绝）：

```python
from ai.nl2sql.sql_generator import generate_sql
from ai.nl2sql.result_explainer import explain_result
from backend.services.hive_client import query

result = generate_sql(user_question)

# ⚠️ 处理非数据问题的安全拒绝
if result["sql"] == "UNABLE_TO_ANSWER":
    yield f"data: {json.dumps({'type': 'text', 'content': '抱歉，我目前只能回答数据分析相关的问题。'})}\n\n"
    return

df = query(result["sql"])
answer = explain_result(user_question, result["sql"], df)
```

> 将来接 `chat.py` 时直接参考这段，比 TODO 注释更精确。

### 3.6 B 模块完成情况（v2.0）

| 模块 | 状态 | C 是否需要 |
|------|------|-----------|
| `ai/llm_client.py` | ✅ | 间接（B 模块内部依赖） |
| `ai/chat_demo.py` | ✅ | 不必须（快速体验 LLM） |
| `ai/insights.py` | ✅ 已接入 | kpi/cards 惰性导入（无 LLM key 静默跳过） |
| `ai/nl2sql/schema_context.py` | ✅ | 不直接调 |
| `ai/nl2sql/sql_generator.py` | ✅ | **必须**（chat.py 核心） |
| `ai/nl2sql/result_explainer.py` | ✅ | **必须**（chat.py 核心） |
| `ai/agent/tools.py` | ✅ 已适配 | `_get()` 自动解包 C 的 `{code,message,data}`，Agent 直接拿业务字段 |
| `ai/agent/analysis_agent.py` | ✅ | B 已完成（C 无需改，依赖 tools.py 返回） |
| `analysis/rfm_model.py` | ✅ | 导入数据（MySQL） |
| `analysis/recommender.py` | ✅ | 导入数据（MySQL） |
| `analysis/xgboost_model.py` | ✅ | 答辩 PPT 用，C 不需要 |

---

## 四、C 交付状态

### ✅ C 已完成（无需再动）

| 类别 | 内容 |
|------|------|
| REST 接口 | kpi/trend/top/funnel/rfm/recommend/report(latest+history) — Mock/Real 双模式 |
| SSE 接口 | /api/chat（流式对话 + 多轮上下文 + 频率限制）、/api/report/stream（晨报实时推送） |
| 鉴权 | Bearer Token（可选开启，_auth.py 装饰器 + app.py before_request） |
| 定时任务 | APScheduler 每日 8:00 触发晨报 + 钉钉推送 + SSE 通知 |
| 参数校验 | days/category 非法值返回 400 |
| 数据安全 | sort_by 白名单防注入、category int() 强转 |
| KPI | 4 项环比（dau/orders/conversion/avg_pv）+ AI 洞察 |
| RFM | Mock 恢复 + 真实模式动态取 MAX(dt) |
| Chat | B 的 smart_chat 混合路由 + generate_sql 降级 + 频率限制 + 饼图推断 |
| 连接池 | MySQL DBUtils PooledDB（回退兼容） |
| 日志 | RotatingFileHandler 轮转 |
| 内存泄漏 | SSE 订阅者 unsubscribe 清理 |
| 依赖 | requirements.txt 完整（含 apscheduler/requests/DBUtils） |

### ⏳ 等别人（C 管不了）

| 依赖 | 对方交付后 C 做什么 |
|------|-------------------|
| A | Hive 表建好后切 `USE_REAL_DATA=true`，真实链路即可跑通 |
| B | `ai/morning_report.py` 完成后 scheduler 真实生成晨报（当前 Mock 打日志） |
| D | 前端联调反馈 → C 修接口 bug |
