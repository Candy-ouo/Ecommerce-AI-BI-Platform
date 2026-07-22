# B模块交付文档 —— AI + 算法模型

> **负责人：B**  
> **分支：feature/b-ai-ml**  
> **最后更新：2026-07-20**

---

## 一、文件清单

```
ai/
├── llm_client.py              ✅ LLM API 统一封装
├── chat_demo.py               ✅ 命令行对话 Demo
├── insights.py                ✅ AI 数据洞察（KPI→分析报告）
├── nl2sql/
│   ├── schema_context.py      ✅ 解析 schema.md → Prompt 上下文
│   ├── sql_generator.py       ✅ 自然语言 → Hive SQL
│   └── result_explainer.py    ✅ SQL 结果 → 自然语言解读
├── morning_report.py          ✅ 智能晨报（环比异常+三段式报告）
└── agent/
    ├── tools.py               ✅ 5个工具函数（HTTP调C的API）
    └── analysis_agent.py      ✅ ReAct Agent（多步推理分析）

analysis/
├── rfm_model.py               ✅ RFM 用户价值分群
├── xgboost_model.py           ✅ XGBoost 复购预测
└── recommender.py             ✅ Item-CF 协同过滤 + 推荐理由

data/                           （生成数据，不提交）
├── rfm_result.csv             ✅ （RFM 产出）
├── recommend_result.csv       ✅ （推荐产出，含reason字段）
├── xgboost_repurchase_model.pkl  ✅ （XGBoost 模型）
└── shap_summary.png           ✅ （特征重要性图）
```

---

## 二、每个模块详解

---

### 2.1 `ai/llm_client.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 阿里云百炼通义千问 API 统一封装，提供 `chat()` 和 `chat_stream()` |
| **谁用** | B 自己的其他 AI 模块 + **C 的 chat.py** |
| **依赖** | `pip install openai python-dotenv` |
| **配置** | `.env` 中设置 `QWEN_API_KEY` |
| **自检** | `python ai/llm_client.py` |

**C 怎么用：**
```python
from ai.llm_client import get_llm_client
llm = get_llm_client()
answer = llm.chat("你好")
# 流式（SSE）
for chunk in llm.chat_stream("讲个故事"):
    print(chunk, end="")
```

---

### 2.2 `ai/nl2sql/schema_context.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 读取 A 的 `docs/schema.md` → 提取 14 张表 + 全部字段 → 生成 LLM Prompt 可用的结构化文本 |
| **谁用** | `sql_generator.py` |
| **依赖** | `docs/schema.md`（A 产出） |
| **自检** | `python ai/nl2sql/schema_context.py`（打印生成的 Schema 文本） |

**怎么用：**
```python
from ai.nl2sql.schema_context import get_schema_text
schema_text = get_schema_text()  # 返回整个 Schema 的文本表示
```

---

### 2.3 `ai/nl2sql/sql_generator.py` ⭐ 核心

| 项目 | 内容 |
|------|------|
| **干什么** | 接收自然语言问题 → 动态匹配 Few-shot 示例 → 组装 Prompt → 调 LLM → **返回可执行的 Hive SQL** |
| **谁用** | **C 的 `chat.py`**（核心依赖，救命清单项） |
| **依赖** | `llm_client.py` + `schema_context.py` |
| **自检** | `python ai/nl2sql/sql_generator.py`（6 条测试问题） |

**C 怎么用：**
```python
from ai.nl2sql.sql_generator import generate_sql
result = generate_sql("最近3天购买量最高的5个类目")
# → {"sql": "SELECT item_category, SUM(buy_cnt)...", "raw": "LLM原始返回"}

# ⚠️ C 需要处理 UNABLE_TO_ANSWER 情况
if result["sql"] == "UNABLE_TO_ANSWER":
    return "抱歉，这个问题我无法回答，请尝试问数据分析相关的内容。"
```

**Prompt 架构（答辩亮点）：**

`SYSTEM_PROMPT` 采用 6 模块分层设计：

| 模块 | 内容 | 作用 |
|------|------|------|
| Role | Senior Data Engineer 角色定义 | 设定能力边界 |
| Context | 数据环境、时间范围、行为编码 | 提供业务上下文 |
| Critical Rules | dt 分区必加、UV=DISTINCT 等硬约束 | 避免低级 SQL 错误 |
| Reasoning Process | 6 步推理引导（意图识别→选表→选字段→条件→聚合→拼SQL） | 提升复杂查询准确率 |
| Output Format | 只输出 SQL，非数据问题返回 UNABLE_TO_ANSWER | 安全拒绝，避免幻觉 |
| Edge Cases | 日期推算、默认值、越界处理 | 边界情况覆盖 |

**动态 Few-shot 匹配：** 14 条示例按 6 类索引（trend/ranking/aggregate/funnel/filter/kpi），根据用户问题关键词自动匹配 2-3 条最相关示例。

**测试通过率：6/6（100%）**
```
Q: 12月18日有多少活跃用户？                     → aggregate ✅
Q: 最近7天的DAU趋势                             → trend     ✅
Q: 购买量最高的10个类目                           → ranking   ✅
Q: 12月18日的全站转化漏斗数据                     → funnel    ✅
Q: 品类4245最近3天的购买量                        → filter    ✅
Q: 今天天气怎么样                                → UNABLE_TO_ANSWER ✅
```

---

### 2.4 `ai/nl2sql/result_explainer.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 把 SQL 查询结果（DataFrame）→ 转成自然语言中文回答 |
| **谁用** | **C 的 `chat.py`**（SQL 执行完后调用） |
| **依赖** | `llm_client.py` |
| **Prompt 结构** | Role → Context → Output Format → Constraints（4 模块） |
| **自检** | `python ai/nl2sql/result_explainer.py`（Mock 数据测试） |

**C 怎么用：**
```python
from ai.nl2sql.result_explainer import explain_result
# df 是执行 SQL 返回的 Pandas DataFrame
answer = explain_result(question, sql, df)
# → "近3天购买量最高的类目是 ID 4245（2,800件），
#    其次是 ID 8270（2,100件）..."
```

**C 的 chat.py 完整调用链路：**
```python
from ai.nl2sql.sql_generator import generate_sql
from ai.nl2sql.result_explainer import explain_result
from backend.services.hive_client import query

result = generate_sql(user_question)   # → {"sql": "..."}
df = query(result["sql"])              # → DataFrame
answer = explain_result(user_question, result["sql"], df)  # → 中文回答
```

---

### 2.5 `ai/insights.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 输入 KPI 指标字典 → LLM 生成三段式分析报告（核心指标概览 + 趋势异常 + 运营建议） |
| **谁用** | C（可选，增强任意 API 返回值的可读性） |
| **依赖** | `llm_client.py` |
| **自检** | `python ai/insights.py` |

**怎么用：**
```python
from ai.insights import generate_insights
kpi = {"dau": 8230, "total_orders": 3900, "buy_conversion": 0.377, ...}
report = generate_insights(kpi)
# → 三段式中文分析报告，约 200-300 字
```

---

### 2.6 `ai/chat_demo.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 命令行 AI 对话程序，输入文字就聊天，支持多轮上下文记忆 |
| **谁用** | 任何人快速体验百炼大模型 |
| **怎么用** | `python ai/chat_demo.py`，输入 `quit` 退出 |

---

### 2.7 `analysis/rfm_model.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 分块读 1225 万行 CSV → 计算 R/F/M 三维分值 → 三分位打分 → 8 类标签 |
| **产出** | `data/rfm_result.csv`（10,000 用户） |
| **给谁** | **C 导入 MySQL** → `GET /api/rfm/dist` → D 前端饼图 |
| **耗时** | ~36 秒 |
| **自检** | `python analysis/rfm_model.py` |

**C 使用方法：**
```sql
LOAD DATA LOCAL INFILE 'data/rfm_result.csv'
INTO TABLE rfm_result FIELDS TERMINATED BY ',' IGNORE 1 ROWS;
```

**8 类分布：**
```
新锐潜力用户 4,443 | 重要价值用户 2,558 | 低价值用户 1,337
浏览型用户 1,114 | 重要挽留用户 234 | 重要发展用户 150
重要保持用户 125 | 其他 39
```

---

### 2.8 `analysis/xgboost_model.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 时间切分（前24天→特征,后7天→标签）→ 20维特征工程 → XGBoost 训练 → 评估 |
| **产出** | `data/xgboost_repurchase_model.pkl` + `data/shap_summary.png` |
| **给谁** | **答辩 PPT 用**（AUC 截图 + 特征重要性图） |
| **耗时** | ~3 分钟 |
| **模型效果** | AUC=0.748, Precision=0.849, F1=0.760 |
| **自检** | `python analysis/xgboost_model.py` |

---

### 2.9 `analysis/recommender.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 提取 12 万条购买记录 → 构建 User-Item 稀疏矩阵 → 余弦相似度 → 每人 Top10 推荐 + 推荐理由 |
| **产出** | `data/recommend_result.csv`（4,331 用户 × 32,971 条，含 reason 字段） |
| **给谁** | **C 导入 MySQL** → `GET /api/recommend?user_id=xxx` → D 前端推荐列表 |
| **耗时** | ~9 秒 |
| **自检** | `python analysis/recommender.py` |

**产出 CSV 格式：**
```csv
user_id,item_id,score,reason
4913,106533518,0.8165,与您购买过的商品361346418偏好相似（相似度0.82）
```
每条推荐记录来源商品（贡献最高相似度的已购商品），实现可解释推荐。

---

### 2.10 `ai/agent/tools.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 定义 5 个 Agent 工具函数，通过 HTTP 请求调用 C 的后端 API |
| **谁用** | `analysis_agent.py` |
| **依赖** | `pip install requests` + C 的 Flask 后端启动 |
| **自检** | 先启动 `python backend/app.py`，再 `python ai/agent/tools.py` |

**5 个工具 → C 的 API 映射：**

| 工具 | C 接口 | 测试 |
|------|--------|------|
| `get_daily_kpi()` | `GET /api/kpi/cards` | ✅ |
| `get_active_trend(days)` | `GET /api/trend/active?days=N` | ✅ |
| `get_top_items(limit, sort_by)` | `GET /api/top/items?limit=N&sort_by=pv` | ✅ |
| `get_funnel()` | `GET /api/funnel` | ✅ |
| `get_rfm_distribution()` | `GET /api/rfm/dist` | ✅ |

**C 怎么用：** 不需要直接调 tools.py，Agent 内部自动调用。

---

### 2.11 `ai/agent/analysis_agent.py`

| 项目 | 内容 |
|------|------|
| **干什么** | ReAct 风格 Agent：接收高层级分析任务 → 自动规划工具调用 → 多步获取数据 → LLM 汇总生成分析报告 |
| **谁用** | **C 的 `chat.py`**（可选增强模式） |
| **依赖** | `tools.py` + `llm_client.py` |
| **自检** | 启动 Flask 后 `python ai/agent/analysis_agent.py` |

**Prompt 架构：** Role → Context → 工具表(含When to Use) → 工具选择策略 → Protocol → 报告质量标准(Good/Bad Example) → 边界处理

**动态路标：** 根据任务关键词自动生成 Strategy Hint，引导 LLM 优先选择最相关的工具。

**测试通过：2/2**
```
Task: "分析用户转化情况" → get_funnel → 268字报告 ✅
Task: "判断是否需要用户召回" → get_rfm_distribution → 280字报告 ✅
```

---

### 2.12 `ai/morning_report.py`

| 项目 | 内容 |
|------|------|
| **干什么** | 每日 8:00 自动生成运营晨报：读取 KPI → 环比 7 天前 → 检测 ±10% 异常 → LLM 生成三段式报告 |
| **谁用** | **C 的 `scheduler.py`** 每日定时调用 |
| **依赖** | `llm_client.py` |
| **自检** | `python ai/morning_report.py` |

**Prompt 架构：** Role(Chief Data Analyst, 给CEO汇报) → Context → CoT(4问) → Output Format → Constraints(禁止虚构+Bad/Good Example)

**C 怎么用：**
```python
from ai.morning_report import generate_report
report = generate_report()
# → {"date": "2014-12-18", "content": "三段式报告...", "anomalies": ["DAU上升52.4%..."]}
db.save_report(report)  # 存 MySQL → GET /api/report/latest
```

---

## 三、环境配置

```bash
# 1. 安装依赖
pip install openai python-dotenv pandas numpy xgboost scikit-learn scipy

# 2. 配置 .env
echo 'QWEN_API_KEY=sk-你的百炼key' > .env

# 3. 验证
python ai/llm_client.py
```

---

## 四、C 集成指南

**C 需要 import 的模块：**

| 模块 | import 语句 | 什么时候用 |
|------|------------|------------|
| LLM 客户端 | `from ai.llm_client import get_llm_client` | 直接调 LLM |
| NL2SQL | `from ai.nl2sql.sql_generator import generate_sql` | `/api/chat` 入口 |
| 结果解读 | `from ai.nl2sql.result_explainer import explain_result` | SQL 执行完 |
| AI 洞察 | `from ai.insights import generate_insights` | 增强 API 返回值 |

**`/api/chat` 完整调用链路：**
```python
from ai.nl2sql.sql_generator import generate_sql
from ai.nl2sql.result_explainer import explain_result
from backend.services.hive_client import query

result = generate_sql(user_question)

# ⚠️ 处理非数据问题的安全拒绝
if result["sql"] == "UNABLE_TO_ANSWER":
    yield "data: " + json.dumps({"type": "text", "content": "抱歉，我目前只能回答数据分析相关的问题。"}) + "\n\n"
    return

df = query(result["sql"])
answer = explain_result(user_question, result["sql"], df)
```

---

## 五、Prompt 架构说明（答辩亮点）

两个 NL2SQL 模块均采用分层 Prompt Engineering 设计：

| 模块 | Prompt 结构 | 亮点 |
|------|------------|------|
| `sql_generator` | Role → Context → Critical Rules → CoT(6步推理) → Output Format → Edge Cases | 6 模块 + 动态 Few-shot(14条示例按关键词匹配) + 安全拒绝 |
| `result_explainer` | Role → Context → Output Format → Constraints | 4 模块，输出简洁中文解读 |

---

## 五、自检清单（一键验证全部模块）

```bash
cd Ecommerce-AI-BI-Platform

# AI 模块
python ai/llm_client.py                    # LLM 链路
python ai/nl2sql/schema_context.py         # Schema 解析
python ai/nl2sql/sql_generator.py          # NL2SQL 生成（6/6）
python ai/nl2sql/result_explainer.py       # 结果解读
python ai/insights.py                      # 数据洞察
python ai/morning_report.py                # 智能晨报

# Agent（需先启动 C 的 Flask: python backend/app.py）
python ai/agent/tools.py                   # 工具函数（5/5）
python ai/agent/analysis_agent.py          # Agent 多步分析（2/2）

# 算法模型
python analysis/rfm_model.py               # RFM（~36s）
python analysis/xgboost_model.py           # XGBoost（~3min）
python analysis/recommender.py             # Item-CF（~9s）
```

---

## 六、全部完成

B 模块 12 个文件全部交付，无待完成项。

| 分类 | 数量 | 文件 |
|------|------|------|
| AI 封装 | 1 | llm_client.py |
| NL2SQL | 3 | schema_context.py, sql_generator.py, result_explainer.py |
| Agent | 2 | tools.py, analysis_agent.py |
| AI 洞察 | 3 | insights.py, morning_report.py, chat_demo.py |
| 算法模型 | 3 | rfm_model.py, xgboost_model.py, recommender.py |

---

## 七、模型产出文件

| 文件 | 生成方式 | 大小 | 用途 |
|------|---------|------|------|
| `data/rfm_result.csv` | `python analysis/rfm_model.py` | ~500KB | C 导入 MySQL |
| `data/recommend_result.csv` | `python analysis/recommender.py` | ~1.2MB | C 导入 MySQL |
| `data/xgboost_repurchase_model.pkl` | `python analysis/xgboost_model.py` | ~300KB | 答辩展示 |
| `data/shap_summary.png` | `python analysis/xgboost_model.py` | 107KB | 答辩 PPT |
