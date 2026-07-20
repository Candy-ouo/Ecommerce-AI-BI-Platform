"""
NL2SQL 核心：自然语言 → Spark SQL

接收用户自然语言问题，调用 LLM 生成可执行的 Hive SQL。

使用方式（C 在 chat.py 中这样调用）：
    from ai.nl2sql.sql_generator import generate_sql
    result = generate_sql("最近3天购买量最高的5个类目")
    # → {"sql": "SELECT item_category, SUM(buy_cnt)...", "raw": "..."}

前置依赖：
    ai.llm_client        — LLM 调用
    ai.nl2sql.schema_context — 表结构上下文
"""

import re
import sys
import logging
from pathlib import Path
from typing import Optional

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai.llm_client import get_llm_client
from ai.nl2sql.schema_context import get_schema_text

logger = logging.getLogger(__name__)

# ============================================================
# Prompt 模板
# ============================================================

SYSTEM_PROMPT = """You are a professional data analyst assistant specializing in e-commerce user behavior analysis.
Your job is to convert natural language questions into correct Hive SQL queries.

CONTEXT:
- Database: ecommerce_bi (all tables are in this database)
- Data period: 2014-11-18 to 2014-12-18 (31 days)
- TODAY / "latest" / "most recent" refers to 2014-12-18
- behavior_type encoding: 1=browse, 2=fav, 3=cart, 4=buy
- ALL partitioned tables MUST have dt filter (WHERE dt = 'YYYY-MM-DD' or BETWEEN)
- Use Hive/Spark SQL syntax (not MySQL)
- Table and column names are CASE SENSITIVE as provided

RULES:
1. Output ONLY the SQL query, nothing else.
2. Do NOT wrap SQL in markdown code blocks (no ```sql, no ```).
3. Use the exact table and column names from the schema.
4. Always add a dt partition filter for partitioned tables.
5. Use COUNT(DISTINCT user_id) for UV/DAU calculations.
6. Use SUM(buy_cnt) not COUNT(*) for purchase aggregations from summary tables.
7. When the user asks about "trend" or "over time", GROUP BY dt ORDER BY dt.
8. When comparing dates, use dt BETWEEN 'start' AND 'end'.
9. Use LIMIT for TopN queries.
10. Return plain SQL as a single statement, terminated with semicolon."""


def _build_user_prompt(question: str, schema_text: str) -> str:
    """组装发送给 LLM 的完整 prompt"""
    return f"""{schema_text}

---

USER QUESTION:
{question}

Generate the correct Hive SQL query:"""


# ============================================================
# SQL 清理
# ============================================================

def _clean_sql(raw: str) -> str:
    """从 LLM 返回值中提取纯净 SQL"""
    sql = raw.strip()

    # 去掉 markdown 代码块
    m = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", sql, re.DOTALL)
    if m:
        sql = m.group(1).strip()

    # 去掉 LLM 有时会加的前缀文字（如 "Here is the SQL:"）
    # 找第一个 SELECT / WITH / INSERT / SHOW 关键字
    keywords = ["SELECT", "WITH", "INSERT", "SHOW", "DESC"]
    for kw in keywords:
        idx = sql.upper().find(kw)
        if idx >= 0:
            sql = sql[idx:]
            break

    # 去掉末尾多余分号后面的内容
    semi_idx = sql.rfind(";")
    if semi_idx >= 0:
        sql = sql[:semi_idx + 1]

    return sql.strip()


# ============================================================
# 公共接口
# ============================================================

def generate_sql(
    question: str,
    schema_text: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    将自然语言问题转换为 Hive SQL。

    Args:
        question:    用户自然语言问题（如 "最近3天购买量最高的5个类目"）
        schema_text: 自定义 Schema 文本（不传则自动从 schema.md 构建）
        model:       覆盖模型（如 "qwen-max"）

    Returns:
        {
            "sql": "SELECT item_category, SUM(buy_cnt)...",  # 可执行的 SQL
            "raw": "..."                                      # LLM 原始返回
        }
    """
    llm = get_llm_client()

    # 获取 Schema 上下文
    if schema_text is None:
        schema_text = get_schema_text()
        logger.info("Schema text loaded: %d chars", len(schema_text))

    user_prompt = _build_user_prompt(question, schema_text)

    # 调用 LLM（低温度保证 SQL 稳定）
    raw = llm.chat(prompt=user_prompt, system_prompt=SYSTEM_PROMPT, temperature=0.05)

    sql = _clean_sql(raw)

    logger.info("Question: %s", question)
    logger.info("Generated SQL: %s", sql)

    return {"sql": sql, "raw": raw}


# ============================================================
# 命令行测试
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    test_questions = [
        "12月18日有多少活跃用户？",
        "最近7天的DAU趋势",
        "购买量最高的10个类目",
        "12月18日的全站转化漏斗数据",
    ]

    for q in test_questions:
        print(f"\n{'=' * 60}")
        print(f"Q: {q}")
        result = generate_sql(q)
        print(f"SQL: {result['sql']}")
