# 基于大数据的电商用户行为分析与AI智能BI平台

## 项目简介

本项目基于阿里天池Mobile Recommendation真实电商用户行为数据集（1225万条行为记录），构建一个集**大数据批处理、机器学习建模、AI大模型交互**于一体的电商用户行为分析与智能BI平台。

## 技术栈

| 层次 | 技术 |
|------|------|
| 数据存储 | Hive + HDFS (Parquet) |
| 数据计算 | Spark SQL / PySpark |
| 后端 | Flask + PyHive |
| 数据库 | MySQL |
| 前端 | 原生 HTML/CSS/JS + ECharts |
| AI/ML | DeepSeek/Qwen API + XGBoost + Scikit-learn |
| AI Agent | LangChain |

## 快速启动

### 1. 环境准备

```bash
# 安装 Python 依赖
pip install -r backend/requirements.txt

# 配置后端环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env 填写你的 Hive/MySQL/LLM API 连接信息

# 同时拷贝一份到项目根目录（AI 模块需要读取）
cp backend/.env .env
```

### 2. 数据导入

```bash
# 将数据集CSV放入 data/ 目录
# 运行清洗 + 导入Hive
python etl/clean_data.py        # 数据清洗
python warehouse/run_etl.py     # 数仓建表+ETL
```

### 3. 启动后端

```bash
cd backend
python app.py
```

### 4. 打开前端

浏览器打开 `frontend/index.html`，即可看到数据大屏。

## 目录结构

```
ecommerce-ai-bi/
├── data/           # 数据集（gitignore）
│   ├── README.md   # 数据说明
│   └── sample/     # 开发样本（1万条）
├── etl/            # 数据清洗与质量检测
├── warehouse/      # 数仓建表与ETL SQL
├── analysis/       # 机器学习模型（RFM/XGBoost/Item-CF）
├── ai/             # AI模块（NL2SQL/Agent/洞察）
│   ├── nl2sql/     # 自然语言转SQL
│   └── agent/      # AI Agent
├── backend/        # Flask API服务
│   ├── api/        # REST API接口
│   └── services/   # Hive/MySQL连接封装
├── frontend/       # 前端大屏（HTML/CSS/JS + ECharts）
├── tests/          # 测试用例
├── docs/           # 文档与答辩PPT
├── .env.example    # 环境变量模板
├── .gitignore
└── README.md
```

## 团队分工

| 角色 | 负责 | 说明 |
|------|------|------|
| A | 数仓架构 | warehouse/ + docs/schema.md |
| B | AI+算法 | ai/ + analysis/ |
| C | 后端 | backend/ + README |
| D | 前端 | frontend/ + PPT |
| E | 数据+测试 | etl/ + tests/ + data/README.md |

## 文档

- [需求文档](docs/requirements.md)
- [开发计划](docs/DEV_PLAN.md)
- [表结构文档](docs/schema.md)（A产出）
- [AI设计文档](docs/ai_design.md)（B产出）
- [测试报告](docs/testing_report.md)（E产出）
