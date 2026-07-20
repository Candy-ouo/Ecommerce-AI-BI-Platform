# C 模块交付说明 —— 后端 API + 数据接入

负责人：C
分支：`feature/c-backend`
最后更新：2026-07-20（同步 B 的 ai_design.md v2.0）

---

## 一、文件清单（backend/）

```
backend/
├── app.py                 ← Flask 入口，注册所有 Blueprint，CORS
├── config.py              ← 统一配置（Hive/MySQL/LLM/Flask/数据开关）
├── api/
│   ├── __init__.py        ← Blueprint 注册
│   ├── kpi.py             ← GET  /api/kpi/cards
│   ├── trend.py           ← GET  /api/trend/active
│   ├── top.py             ← GET  /api/top/items
│   ├── funnel.py          ← GET  /api/funnel
│   ├── rfm.py             ← GET  /api/rfm/dist
│   ├── recommend.py       ← GET  /api/recommend?user_id=
│   └── chat.py            ← POST /api/chat（SSE 流式，待接 B 模块）
├── services/
│   ├── hive_client.py     ← pyhive 查询封装
│   ├── db.py              ← MySQL 封装（RFM/推荐结果读取）
│   └── queries.py         ← Hive SQL（顶部常量即 A 需确认的表名/字段名）
├── API.md                 ← 接口详细文档（给 D 联调、B 写 tools.py）
└── .env.example           ← 环境变量模板（占位符，不含真实 key）
```

当前状态：7 个接口全部跑通（Mock 模式），前端可联调；`chat.py` 为 Mock SSE，待 B 的 AI 模块接入。

---

## 二、给各角色的对接说明

### 2.1 给 D（前端）

> C 的后端 7 个接口已全部跑通（Mock 模式）。文档在 `backend/API.md`。
> 本地启动：`cd backend && pip install -r requirements.txt && python app.py`，然后访问 `http://localhost:5000/api/kpi/cards` 等即可联调。
> 接口形状已锁定，按文档对接就行，**尽量不改字段名**。

---

### 2.2 给 B（AI）

> 接口端点清单在 `backend/API.md` 末尾（`tools.py` 调用示例已写好）。
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
| 日 KPI | `ads_daily_kpi` | dt, dau, orders, conversion_rate, avg_pv |
| 全站日 | `dws_platform_day` | dt, dau, pv |
| 商品日 | `dws_item_day` | dt, item_id, pv, fav, buy |
| 漏斗 | `ads_funnel` | dt, pv, fav, cart, buy |

> 另外 C 的 `rfm.py` / `recommend.py` 从 **MySQL** 读（B 模型产出、你建表写入），
> 这两张表（RFM 结果表、推荐结果表）的表名/字段也请一并确认。最终以你的 `docs/schema.md` 为准。

---

## 三、从 B 的 AI 设计文档中，C 需注意 / 可复用的点

### 3.1 RFM 真实标签（接真实数据时替换 Mock）

B 的 `rfm_model.py` 产出 8 类标签（与 C 当前 Mock 命名不同），C 的 `GET /api/rfm/dist` 接真实数据时要按 B 的真实标签返回：

| 标签 | 人数 | 占比 |
|------|------|------|
| 新锐潜力用户 | 4,443 | 44.4% |
| 重要价值用户 | 2,558 | 25.6% |
| 低价值用户 | 1,337 | 13.4% |
| 浏览型用户 | 1,114 | 11.1% |
| 重要挽留用户 | 234 | 2.3% |
| 重要发展用户 | 150 | 1.5% |
| 重要保持用户 | 125 | 1.3% |
| 一般发展/价值用户 | 39 | 0.4% |

> B 的 `rfm_result.csv` 字段：`user_id, R, F, M, R_score, F_score, M_score, rfm_label`
> C 导入 MySQL 的 `rfm_result` 表后，接口读取 `rfm_label` 作 labels、`COUNT(*)` 作 counts。

### 3.2 推荐结果结构（接真实数据时补 reason）

B 的 `recommender.py` 产出 `recommend_result.csv` 字段：`user_id, item_id, score`（**无 reason 列**）。
C 的 `GET /api/recommend` 接真实数据时，`reason` 由 C 自行补全（如 `"协同过滤"`）。

### 3.3 数据导入 MySQL 参考（B 提供）

```sql
LOAD DATA LOCAL INFILE 'data/rfm_result.csv'
INTO TABLE rfm_result
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
IGNORE 1 ROWS;
```

### 3.4 `ai/insights.py`（新完成，可选接入）

B 新增了 AI 数据洞察模块：输入 KPI 字典 → LLM 生成三段式中文分析报告（核心指标概览 + 趋势异常 + 运营建议）。

```python
from ai.insights import generate_insights
kpi = {"dau": 8230, "total_orders": 3900, "buy_conversion": 0.377}
report = generate_insights(kpi)  # → 约 200-300 字中文分析
```

> C 可在 `/api/kpi/cards` 或 `/api/trend/active` 返回时附带 AI 分析文本，增强前端可读性。非必须。

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
| `ai/insights.py` | ✅ | 可选（增强 API 返回值） |
| `ai/nl2sql/schema_context.py` | ✅ | 不直接调 |
| `ai/nl2sql/sql_generator.py` | ✅ | **必须**（chat.py 核心） |
| `ai/nl2sql/result_explainer.py` | ✅ | **必须**（chat.py 核心） |
| `ai/agent/tools.py` | ⬜ | 等 B（需 C 提供 API 地址） |
| `ai/agent/analysis_agent.py` | ⬜ | 等 B |
| `analysis/rfm_model.py` | ✅ | 导入数据（MySQL） |
| `analysis/recommender.py` | ✅ | 导入数据（MySQL） |
| `analysis/xgboost_model.py` | ✅ | 答辩 PPT 用，C 不需要 |

---

## 四、C 的下一步（依赖项）

| 依赖 | 对方交付后 C 做什么 |
|------|-------------------|
| A | 确认表名/字段 → 改 `queries.py` 顶部常量 → `USE_REAL_DATA=true` 切真实数据 |
| B | `ai/` 模块推送 → `chat.py` 按 3.5 节接入 `generate_sql` + `explain_result`；MySQL 导入 RFM/推荐 CSV |
| D | 前端联调反馈 → C 修接口 bug |
