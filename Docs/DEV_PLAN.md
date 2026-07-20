# 🔥 有AI版 — 五人工分工、代码结构、开发顺序

---

## 一、代码目录结构（完整）

```
ecommerce-ai-bi/
│
├── data/                            # 数据目录（gitignore，只留README）
│   ├── README.md                    # E 写：数据来源、下载指引、字段说明
│   ├── raw/                         # 原始CSV（不提交）
│   └── sample/                      # 1万条开发样本
│       └── sample_10k.csv           # E 产出（抽1万条，10万条怕跑不动）
│
├── etl/                             # 🔍 E 负责
│   ├── clean_data.py                # 数据清洗脚本（E 在1万条上开发 → A 对全量1225万运行）
│   ├── sample_extract.py            # 全量数据 → 随机抽1万条样本
│   └── data_quality.py              # 数据质量检测
│
├── warehouse/                       # 👑 A 负责
│   ├── 01_ods_ddl.sql               # ODS层建表 + 加载数据
│   ├── 02_dwd_etl.sql               # DWD层清洗SQL
│   ├── 03_dws_agg.sql               # DWS层聚合SQL
│   └── 04_ads_app.sql               # ADS层应用SQL
│
├── analysis/                        # 🧠 B 负责（模型部分）
│   ├── rfm_model.py                 # RFM分群：打分→分箱→8类标签→写MySQL
│   ├── xgboost_model.py             # XGBoost复购预测：特征工程→训练→评估→SHAP
│   └── recommender.py               # Item-CF协同过滤：行为矩阵→相似度→TopN推荐→写MySQL
│
├── ai/                              # 🧠 B 负责（AI部分）
│   ├── llm_client.py                # LLM API统一封装（DeepSeek/Qwen）
│   ├── nl2sql/
│   │   ├── schema_context.py        # 从A的文档读取表结构，构建Prompt上下文
│   │   ├── sql_generator.py         # 自然语言→SQL（调用LLM）
│   │   └── result_explainer.py      # SQL结果→自然语言解读（调用LLM）
│   ├── agent/
│   │   ├── tools.py                 # 定义5个Agent工具函数
│   │   └── analysis_agent.py        # Agent主逻辑：接收任务→规划→调用工具→汇总
│   └── insights.py                  # AI数据洞察：ADS指标→LLM→业务建议
│   └── morning_report.py             # 🔥 智能晨报：定时读ADS→环比对比→LLM生成→推送
│
├── backend/                         # ⚙️ C 负责
│   ├── config.py                    # 配置：Hive连接、MySQL连接、LLM代理地址
│   ├── app.py                       # Flask应用入口，注册所有Blueprint
│   ├── scheduler.py                 # 🔥 定时任务：每天8:00触发晨报生成+推送
│   ├── api/
│   │   ├── __init__.py              # Blueprint注册
│   │   ├── kpi.py                   # GET /api/kpi/cards
│   │   ├── trend.py                 # GET /api/trend/active
│   │   ├── top.py                   # GET /api/top/items
│   │   ├── funnel.py                # GET /api/funnel
│   │   ├── rfm.py                   # GET /api/rfm/dist
│   │   ├── recommend.py             # GET /api/recommend?user_id=xxx
│   │   ├── chat.py                  # POST /api/chat (SSE流式)
│   │   └── report.py                # 🔥 GET /api/report/latest, GET /api/report/history
│   └── services/
│       ├── hive_client.py           # pyhive连接封装，执行SQL返回DataFrame
│       └── db.py                    # MySQL连接 + 常用查询封装
│
├── frontend/                        # 🎨 D 负责
│   ├── index.html                   # 主大屏页面（引入所有JS/CSS）
│   ├── css/
│   │   └── dashboard.css            # 全部样式：布局、卡片、图表容器、聊天气泡
│   ├── js/
│   │   ├── config.js                # API_BASE_URL等配置
│   │   ├── api.js                   # 统一Ajax封装（fetch + 错误处理）
│   │   ├── charts.js                # 5个ECharts图表初始化+渲染
│   │   ├── ai_chat.js               # AI对话面板：发送消息、SSE接收、渲染气泡+图表
│   │   ├── report.js                # 🔥 晨报展示：读取 /api/report/* → 渲染历史晨报列表
│   │   └── main.js                  # 页面入口：初始化图表、定时刷新、事件绑定
│   └── assets/
│       └── logo.png                 # 可选
│
├── tests/                           # 🔍 E 负责
│   ├── test_api.py                  # API接口自动化测试
│   ├── test_nl2sql.py               # NL2SQL准确性测试（20+用例）
│   └── test_data_consistency.py     # 大屏数据一致性测试
│
├── docs/                            # 文档
│   ├── schema.md                    # A 写：全部表结构（给B和C用，最关键的接口文档）
│   ├── ai_design.md                 # B 写：AI模块设计说明
│   ├── testing_report.md            # E 写：测试报告
│   └── ppt/                         # D 负责：答辩PPT
│
├── .env.example                     # C 写：环境变量模板
├── .gitignore
└── README.md                        # C 写：项目整体说明
```

---

## 二、五人分工 + 每人具体要写的代码

---

### 👑 A — 数仓架构师

**前置依赖**：E 产出清洗后的数据 → A 加载到 Hive

**下游被依赖**：B 需要 A 的 schema 文档 → 写 NL2SQL Prompt；C 需要 A 的表名和字段 → 写 API 查询

#### A 要写的文件清单

| # | 文件 | 内容 | 完成后谁来用 |
|---|------|------|-------------|
| 1 | `warehouse/01_ods_ddl.sql` | 建库建表 + LOAD DATA 加载两张 CSV 到 `ods_user_behavior` 和 `ods_item_info` | — |
| 2 | `warehouse/02_dwd_etl.sql` | Hive SQL：去重、类型转换、中文映射 → `dwd_user_behavior` | — |
| 3 | `warehouse/03_dws_agg.sql` | 聚合 SQL：日活表、商品日表、品类日表、留存表 | C（API查这些表） |
| 4 | `warehouse/04_ads_app.sql` | 应用 SQL：RFM结果表、每日KPI表、品类TopN表、漏斗表 | C（API查这些表） |
| 5 | `docs/schema.md` | 🔥 **最关键产出**：每张表的表名、字段名、类型、含义、示例值 | B（NL2SQL）+ C（API） |

#### A 的开发顺序

```
Day 1 上午: 建 ODS 表 → 加载 E 清洗后的数据
Day 1 下午: 写 DWD 清洗 SQL → DWS 聚合 SQL（先写日活和商品表）
Day 2 上午: DWS 补完（品类表、留存表）→ ADS 应用层 SQL
Day 2 下午: 写 docs/schema.md → 发给 B 和 C
Day 3 上午: 数据校验 → 配合 C 调优慢 SQL
Day 3 下午: 写答辩 PPT 数仓部分
```

---

### 🧠 B — AI + 算法工程师（任务最重）

**前置依赖**：A 的 `docs/schema.md` → B 才能写 NL2SQL Prompt；E 的样本数据 → B 才能训模型

**下游被依赖**：C 的后端 `/api/chat` 调用 B 的 `sql_generator`、`result_explainer`、`analysis_agent`

#### B 要写的文件清单

| # | 文件 | 内容 | 提供给 |
|---|------|------|--------|
| 1 | `ai/llm_client.py` | 封装 LLM API 调用：`chat(prompt)`返回文本；处理超时/重试/限流；支持切换 DeepSeek/Qwen | 所有 AI 模块 |
| 2 | `ai/nl2sql/schema_context.py` | 读取 `docs/schema.md` → 构建结构化的表结构描述 → 生成 Prompt 用的 schema 文本 | `sql_generator.py` |
| 3 | `ai/nl2sql/sql_generator.py` | `generate_sql(question: str) -> dict`：组装 Prompt → 调 LLM → 解析出 SQL → 返回 `{sql, raw_response}` | C（`/api/chat`） |
| 4 | `ai/nl2sql/result_explainer.py` | `explain_result(question, sql, result_df) -> str`：将查询结果 + 原始问题 → LLM → 自然语言回答 | C（`/api/chat`） |
| 5 | `ai/agent/tools.py` | 定义 5 个 Tool 函数，每个函数通过 HTTP 调用 C 的 API | `analysis_agent.py` |
| 6 | `ai/agent/analysis_agent.py` | `run_agent(task: str) -> str`：LangChain Agent 初始化 + 工具注册 + 执行 | C（`/api/chat`） |
| 7 | `ai/insights.py` | `generate_insights(kpi_data: dict) -> str`：输入ADS指标 → LLM → 业务建议 | C |
| 8 | `ai/morning_report.py` | 🔥 `generate_report() -> str`：读取 ADS 昨日指标 → 环比 7 天前 → 识别 ±10% 异常 → LLM 生成 200-300 字晨报 → 返回；历史报告存 MySQL | C（`/api/report/*` + scheduler） |
| 9 | `analysis/rfm_model.py` | Pandas 读取数据 → R/F/M 计算 → 三分位数分箱 → 8类标签 → 输出 `rfm_result.csv`（C 导入 MySQL） | C |
| 10 | `analysis/xgboost_model.py` | 特征工程 → train/test split → XGBoost 训练 → AUC评估 → SHAP特征重要性图 → 保存模型 | 答辩截图 |
| 11 | `analysis/recommender.py` | 构建 User-Item 矩阵 → 余弦相似度 → TopN → 输出 `recommend_result.csv`（C 导入 MySQL） | C |

#### B 的开发顺序

```
Day 1 上午: llm_client.py（跑通API调用） → schema_context.py（等A的schema一到就写）
Day 1 下午: sql_generator.py（单表查询原型） → 跑通第一个 NL2SQL Demo
Day 2 上午: rfm_model.py → xgboost_model.py（训练+截图）
Day 2 下午: recommender.py → result_explainer.py → insights.py → morning_report.py
Day 3 上午: tools.py → analysis_agent.py（Agent编排）
Day 3 下午: 优化所有Prompt → 准备AI效果对比截图 → 写答辩PPT AI部分
```

> ⚠️ 如果时间紧：Day 2 的 `recommender.py` 可简化为纯协同过滤（不写LLM解释）；Day 3 的 Agent 可降级为预设分析流程图，答辩时口头说明即可。

---

### ⚙️ C — 后端工程师

**前置依赖**：A 的表结构（`docs/schema.md`）→ 写 SQL 查询；B 的 AI 模块 → 集成到 `/api/chat`

**下游被依赖**：D 的前端所有请求都走 C 的 API

#### C 要写的文件清单

| # | 文件 | 内容 | 提供给 |
|---|------|------|--------|
| 1 | `backend/config.py` | Hive连接串、MySQL连接串、LLM代理配置、端口号 | 所有模块 |
| 2 | `backend/services/hive_client.py` | `query(sql)` 函数：pyhive连接 → 执行 → 返回 DataFrame | 所有 API |
| 3 | `backend/services/db.py` | MySQL连接池 + `get_kpi()` / `get_rfm()` 等常用查询 | 所有 API |
| 4 | `backend/api/__init__.py` | 注册所有 Blueprint | `app.py` |
| 5 | `backend/api/kpi.py` | `GET /api/kpi/cards` → 返回 `{dau, gmv, arpu, conversion_rate}` | D（指标卡片） |
| 6 | `backend/api/trend.py` | `GET /api/trend/active?days=7` → 返回日活趋势数组 | D（折线图） |
| 7 | `backend/api/top.py` | `GET /api/top/items?limit=10` → 返回商品热度排行 | D（柱状图） |
| 8 | `backend/api/funnel.py` | `GET /api/funnel` → 返回 `{pv, fav, cart, buy}` 各环节人数 | D（漏斗图） |
| 9 | `backend/api/rfm.py` | `GET /api/rfm/dist` → 返回 8 类用户的占比 | D（饼图） |
| 10 | `backend/api/recommend.py` | `GET /api/recommend?user_id=xxx` → 返回推荐列表 | D（推荐列表） |
| 11 | `backend/api/chat.py` | 🔥 `POST /api/chat`：接收 `{message}` → 调 B 的 `sql_generator` → 执行 SQL → 调 B 的 `result_explainer` → **SSE流式返回** | D（AI对话） |
| 12 | `backend/api/report.py` | 🔥 `GET /api/report/latest`（最新晨报）、`GET /api/report/history?days=7`（历史晨报列表） | D（晨报模块） |
| 13 | `backend/scheduler.py` | 🔥 APScheduler 定时任务：每天 8:00 调 B 的 `morning_report.generate_report()` → 结果存 MySQL →（可选）推送钉钉 Webhook | — |
| 14 | `backend/app.py` | Flask 应用入口 + CORS + Blueprint 注册 + 启动 scheduler | — |
| 15 | `.env.example` | 环境变量模板 | 全员 |
| 16 | `README.md` | 项目说明：快速启动、技术栈、目录结构 | 答辩 |

#### C 的开发顺序

```
Day 1 上午: config.py → hive_client.py → db.py（基础服务层）
Day 1 下午: app.py 骨架 → api/__init__.py → kpi.py（写一个接口验证链路）
Day 2 上午: trend.py → top.py → funnel.py → rfm.py → recommend.py（全部分析接口）
Day 2 下午: chat.py（核心！对接B的AI模块，实现SSE流式）→ report.py + scheduler.py（晨报定时任务）
Day 3 上午: 全接口联调 + Tool注册（供B的Agent调用）+ 晨报推送联调
Day 3 下午: 部署 → README.md → 配合排练
```

---

### 🎨 D — 前端 + 可视化工程师

**前置依赖**：C 的 API 接口文档（至少知道 URL 和返回格式）→ 前端才能对接

**下游被依赖**：无（D 是最终集成者）

#### D 要写的文件清单

| # | 文件 | 内容 |
|---|------|------|
| 1 | `frontend/js/config.js` | `API_BASE_URL`、刷新间隔、图表颜色主题 |
| 2 | `frontend/js/api.js` | 封装 `fetch`，统一错误处理：`fetchKpi()` `fetchTrend()` `fetchTop()` 等 |
| 3 | `frontend/js/charts.js` | 5 个 ECharts 图表：指标卡（HTML数字）、折线图、柱状图、漏斗图、饼图 |
| 4 | `frontend/js/ai_chat.js` | 聊天面板：发送按钮 → POST `/api/chat` → SSE逐字接收 → 渲染气泡 → 检测到图表数据 → 调 `charts.js` 动态渲染 |
| 5 | `frontend/js/report.js` | 🔥 晨报模块：调 `/api/report/latest` 展示今日晨报 → 调 `/api/report/history` 展示历史列表 |
| 6 | `frontend/js/main.js` | 页面初始化：调所有API → 渲染所有图表 → 定时刷新(30s) → 事件绑定 |
| 7 | `frontend/css/dashboard.css` | 全屏网格布局、暗色背景、卡片样式、聊天气泡、晨报卡片、响应式 |
| 8 | `frontend/index.html` | 单页面，引入所有JS/CSS，定义各图表容器DOM + AI对话面板DOM + 🔥晨报区域DOM |

#### D 的开发顺序

```
Day 1 上午: index.html 骨架 → dashboard.css 布局（网格 + 暗色主题）
Day 1 下午: config.js → api.js → charts.js（先用Mock数据渲染3个图表）
Day 2 上午: charts.js 补完5个图表 → 对接C的真接口（一个一个换）
Day 2 下午: ai_chat.js（SSE流式渲染、聊天气泡、图表跟随）
Day 3 上午: report.js（晨报模块）→ 7个模块全联调 → 响应式适配 → 异常状态处理
Day 3 下午: 制作答辩PPT → 录屏备用视频
```

---

### 🔍 E — 数据治理 + 测试

**前置依赖**：原始数据下载完成

**下游被依赖**：A 需要 E 的清洗后数据 → 加载到 Hive；所有人需要 E 的测试报告

#### E 要写的文件清单

| # | 文件 | 内容 | 提供给 |
|---|------|------|--------|
| 1 | `etl/sample_extract.py` | 从 1225 万行随机抽 1 万条 → `data/sample/sample_10k.csv` | 全员开发用 |
| 2 | `etl/clean_data.py` | 🔥 E 在 1 万条上开发调试；通过后交脚本，A 在自己机器对全量 1225 万运行 → `data/processed/` | A（跑全量 + 加载到 Hive） |
| 3 | `etl/data_quality.py` | 质量规则：非空率、唯一率、值域范围 → 输出质量报告 JSON | 答辩展示 |
| 4 | `tests/test_api.py` | 对 C 的全部 8 个 API 做功能测试 + 边界测试 | C（修复bug） |
| 5 | `tests/test_nl2sql.py` | 🔥 20+ 个 NL2SQL 测试用例，覆盖：单表查询、聚合、时间过滤、排序、TopN、多条件组合 → 统计准确率 | B（调Prompt） |
| 6 | `tests/test_data_consistency.py` | 验证大屏展示的数字 = 直接查 Hive 的数字 | D（验证） |
| 7 | `data/README.md` | 数据来源、下载地址、字段字典、清洗规则说明 | 答辩文档 |

#### E 的开发顺序

```
Day 1 上午: sample_extract.py（立刻抽 1 万条发给全员）→ clean_data.py（在 1 万条上开发清洗逻辑）
Day 1 下午: clean_data.py 调试通过 → 脚本交给 A 跑全量 1225 万 → data/README.md
Day 2 上午: data_quality.py → test_api.py（等C的接口出来就开始测）
Day 2 下午: test_nl2sql.py（等B的NL2SQL能跑了就开始测）
Day 3 上午: test_data_consistency.py → 汇总测试报告
Day 3 下午: 补充测试 → 协助D做PPT
```

---

## 三、文件依赖与开发顺序（全局视角）

```
═══════════════════════════════════════════════════════════
阶段 0: 全员准备（Day 1 9:00-10:00）
═══════════════════════════════════════════════════════════

  E: sample_extract.py ──→ 产出 sample_10k.csv ──→ 分发给 A/B/C/D
  A: 初始化 GitHub 仓库结构（创建全部空文件夹）

═══════════════════════════════════════════════════════════
阶段 1: 数据就绪（Day 1 10:00-18:00）
═══════════════════════════════════════════════════════════

  E: clean_data.py（在1万条上写 + 调试）──→ 脚本交给A ──→ A跑全量1225万清洗 ──→ A
                              │
  A: 01_ods_ddl.sql ──→ 02_dwd_etl.sql ──→ 03_dws_agg.sql（先写日活表）
         ↑                      │
         └── E的清洗数据 ────────┘
                              │
  C: config.py → hive_client.py → db.py（等A的第一张表建好就开始测连接）
  
  B: llm_client.py（独立开发，不依赖任何人，先跑通API调用）

  D: index.html + dashboard.css（独立开发，先画布局）

═══════════════════════════════════════════════════════════
阶段 2: 核心联调节点 ⚠️ 关键！(Day 1 晚上 - Day 2 上午)
═══════════════════════════════════════════════════════════

  A 产出 docs/schema.md ──┬──→ B: schema_context.py → sql_generator.py
                          │         （NL2SQL 终于有表结构可以写Prompt了）
                          │
                          └──→ C: 开始写 kpi.py / trend.py 等API
                                   （知道查什么表、什么字段了）

═══════════════════════════════════════════════════════════
阶段 3: 并行开发（Day 2 全天）
═══════════════════════════════════════════════════════════

  A: 03_dws_agg.sql 补完 → 04_ads_app.sql

  B: rfm_model.py → xgboost_model.py → recommender.py
     sql_generator.py → result_explainer.py → insights.py
              │
              └──→ C: chat.py（对接B的AI模块）

  C: kpi.py → trend.py → top.py → funnel.py → rfm.py → recommend.py
                                                              │
              ┌───────────────────────────────────────────────┘
              ↓
  D: charts.js（先用Mock数据，再逐个换成C的真接口）

  E: data_quality.py → test_api.py（C出一个接口E测一个）

═══════════════════════════════════════════════════════════
阶段 4: AI + 前后端联调（Day 2 晚上 - Day 3 上午）
═══════════════════════════════════════════════════════════

  B: tools.py → analysis_agent.py → morning_report.py
         │                              │
         │                              └──→ C: scheduler.py（定时任务调用晨报）
         │         ┌────────────────────────┘
         └──→ C: chat.py（集成Agent）
                  │
                  └──→ D: ai_chat.js（SSE流式联调）+ report.js（晨报联调）

  E: test_nl2sql.py → test_data_consistency.py

═══════════════════════════════════════════════════════════
阶段 5: 收尾（Day 3 下午）
═══════════════════════════════════════════════════════════

  C: 部署全栈 + README.md
  D: 制作PPT + 录屏
  A: 配合D写PPT数仓部分 + 架构图
  B: AI效果对比截图 + 配合D写PPT AI部分
  E: 测试报告 + 辅助PPT
  全员: 排练 15min 汇报
═══════════════════════════════════════════════════════════
```

---

## 四、关键接口契约（团队协作的"合同"）

以下接口一旦确定就不能随便改，改之前必须在群里通知相关人。

### 4.1 A → B + C：表结构文档 `docs/schema.md`

```markdown
## ods_user_behavior (ODS层)
| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| user_id | BIGINT | 用户ID（脱敏） | 98047837 |
| item_id | BIGINT | 商品ID（脱敏） | 232431562 |
| behavior_type | INT | 行为类型 | 1=浏览, 2=收藏, 3=加购, 4=购买 |
| user_geohash | STRING | 用户位置标识（约68%为空） | 95q6awg |
| item_category | BIGINT | 商品分类ID（脱敏） | 4245 |
| time | STRING | 行为时间，精确到小时 | 2014-12-06 02 |

## dwd_user_behavior (DWD层)
（同上格式，逐表列出）

## dws_user_day (DWS层)
（同上，这是B写NL2SQL最核心的表）
...
```

### 4.2 B → C：AI 模块调用方式

```python
# C 在 chat.py 中这样调用 B 的模块：

from ai.nl2sql.sql_generator import generate_sql
from ai.nl2sql.result_explainer import explain_result
from ai.agent.analysis_agent import run_agent
from ai.insights import generate_insights
from backend.services.hive_client import query

# 1. NL2SQL流程
result = generate_sql(user_question)        # → {sql: "...", raw: "..."}
df = query(result["sql"])                   # → DataFrame
answer = explain_result(user_question, result["sql"], df)  # → str

# 2. Agent流程
answer = run_agent(user_task)  # → str（Agent内部自己调API）

# 3. 洞察流程
kpi_data = get_kpi_from_db()
insight = generate_insights(kpi_data)  # → str
```

### 4.3 C → D：API 接口规范

```
GET /api/kpi/cards
→ {"dau": 12345, "dau_change": -0.03, "gmv": 890000, ...}

GET /api/trend/active?days=7
→ {"dates": ["07-14","07-15",...], "dau": [12000,12500,...]}

GET /api/top/items?limit=10&sort_by=pv
→ {"items": [{"name":"商品A","pv":8900}, ...]}

GET /api/funnel
→ {"pv":100000, "fav":35000, "cart":20000, "buy":8000}

GET /api/rfm/dist
→ {"labels":["重要价值","重要发展",...], "counts":[1200,800,...]}

GET /api/recommend?user_id=123
→ {"items":[{"name":"...", "score":0.92, "reason":"..."}, ...]}

POST /api/chat  (SSE)
Body: {"message": "上周销量最高的商品？"}
→ SSE stream: data: {"type":"text","content":"好的，我来查..."}
→ SSE stream: data: {"type":"text","content":"上周销量最高的是..."}
→ SSE stream: data: {"type":"chart","chartType":"bar","data":[...]}
→ SSE stream: data: {"type":"done"}

GET /api/report/latest
→ {"date":"2014-12-18","content":"今日DAU 12,345（环比+3%）...","anomalies":["数码品类转化率下降12%"]}

GET /api/report/history?days=7
→ [{"date":"2014-12-18","content":"...","anomalies":[...]}, ...]
```

### 4.4 E → A：清洗数据交付格式

```
data/processed/user_behavior_clean.csv
编码: UTF-8
分隔符: 逗号
列: user_id, item_id, behavior_type, behavior_type_cn, user_geohash, item_category, behavior_date, behavior_hour
  - behavior_type: 1/2/3/4（原始值保留）
  - behavior_type_cn: 浏览/收藏/加购/购买（中文映射）
  - user_geohash: 约68%为空，保留原值（待定是否删除空列）
  - behavior_date: 2017-11-25
  - behavior_hour: 0~23
```

---

## 五、每日站会议程（10 分钟）

| 时间 | 内容 |
|------|------|
| **9:00** | 每人 1 分钟：昨天做了什么、今天要做什么、遇到什么阻塞 |
| **9:10** | 解决阻塞点（需要谁配合立刻拍板） |
| **21:00** | 各自 PR 提交 + 群里发一句今日完成情况 |

---

## 六、每人的"救命清单"（做不完时的降级方案）

| 人 | 必须完成（不完成项目跑不起来） | 可以降级（答辩口头补） |
|----|---------------------------|---------------------|
| **A** | ODS、DWD、DWS 三张核心表 + `docs/schema.md` | ADS 层可以少写几张，SQL 查询时临时聚合 |
| **B** | `llm_client.py` + `sql_generator.py`（NL2SQL能跑） | Agent 可降级为流程图；XGBoost 可用默认参数 |
| **C** | 全部 7 个API + `chat.py`（AI对话后端能跑） | Tool注册可以硬编码，README 可以从简 |
| **D** | 5 个图表 + AI对话面板（能发能收） | 流式动画可以改成一次性显示 |
| **E** | `sample_extract.py`（1万条）+ `clean_data.py`（在1万条上写逻辑） | A 拿到脚本后自己跑全量 |
