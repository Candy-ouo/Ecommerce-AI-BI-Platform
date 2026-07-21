"""后端统一配置。

团队决策：主数据库用 Hive（pyhive）。A 在 Hive 中建 DWS/ADS 聚合表供 C 直接查询；
B 的 NL2SQL 也生成查 Hive 表的 SQL，chat.py 原样执行。
DB_ENGINE=duckdb 为本地兜底（无 Hive 环境时开发调试用），不影响接口契约。
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── 主数据库引擎开关 ──────────────────────────────────
# hive（默认，接 A 在 Hive 建的 DWS/ADS 聚合表） | duckdb（本地兜底）
DB_ENGINE = os.getenv("DB_ENGINE", "hive")

# ── Hive（pyhive，A 建表、C 直接查聚合表）─────────────
HIVE_HOST = os.getenv("HIVE_HOST", "localhost")
HIVE_PORT = int(os.getenv("HIVE_PORT", "10000"))
HIVE_USER = os.getenv("HIVE_USER", "hive")
HIVE_PASSWORD = os.getenv("HIVE_PASSWORD", "")
HIVE_DATABASE = os.getenv("HIVE_DATABASE", "ecommerce_bi")

# ── DuckDB 本地兜底（DB_ENGINE=duckdb 时启用）────────
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/processed/ecommerce.duckdb")

# ── MySQL（RFM / 推荐结果，B 模型产出、C 只读）────────
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ecommerce_bi")

# ── LLM（命名对齐 B 的 ai_design.md + llm_client.py）──
# B 的 llm_client.py 直接读 os.getenv("QWEN_API_KEY") / os.getenv("QWEN_BASE_URL") / os.getenv("LLM_MODEL")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "qwen")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")

# ── Flask 服务 ──────────────────────────────────────
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"

# ── 数据开关 ────────────────────────────────────────
# Day1: False（接口返回 Mock，保证 Demo 可跑、不依赖 A 的表）
# Day2: A 把聚合表在 Hive 建好 + SCHEMA_CHECKLIST 确认后，改 True 切真 SQL
USE_REAL_DATA = os.getenv("USE_REAL_DATA", "false").lower() == "true"

# ── API 鉴权（Bearer Token）─────────────────────────
# 空字符串 → 鉴权关闭；设置后所有 API 需 Authorization: Bearer <token>
API_TOKEN = os.getenv("API_TOKEN", "")

# ── 晨报推送（钉钉机器人 Webhook）───────────────────
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
