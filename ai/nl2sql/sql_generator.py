"""
NL2SQL 核心：自然语言 → Spark SQL

标准 Prompt Engineering 架构：
  1. Role（角色+能力边界）
  2. Context（数据环境+业务规则）
  3. Dynamic Few-shot（按问题类型匹配 2-3 个示例）
  4. Chain-of-Thought（分步推理：选表→定字段→定条件→拼SQL）
  5. Format（严格输出格式）
  6. Constraints（约束+错误处理）

使用方式（C 在 chat.py 中这样调用）：
    from ai.nl2sql.sql_generator import generate_sql
    result = generate_sql("最近3天购买量最高的5个类目")

前置依赖：
    ai.llm_client        — LLM 调用
    ai.nl2sql.schema_context — 表结构上下文
"""

import re
import sys
import logging
from pathlib import Path
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai.llm_client import get_llm_client
from ai.nl2sql.schema_context import get_schema_text

logger = logging.getLogger(__name__)

# ============================================================
# SYSTEM PROMPT（6 模块合并，一次性读到全貌）
# ============================================================

SYSTEM_PROMPT = """# Role
You are a Senior Data Engineer at a large e-commerce company.
You write production-grade Hive SQL every day.
Your SQL is always correct, partition-aware, and ready to execute.

# Context
- Database: ecommerce_bi
- Engine: Hive / Spark SQL
- Data period: 2014-11-18 to 2014-12-18 (31 days)
- "today" = "latest" = "最近" = "昨天" = 2014-12-18
- behavior_type: 1=浏览, 2=收藏, 3=加购, 4=购买

# Critical Rules (violating any = wrong answer)
1. EVERY partitioned table query MUST filter dt (WHERE dt='...' or BETWEEN)
2. UV/DAU = COUNT(DISTINCT user_id); aggregate tables use SUM(column)
3. Table and column names are CASE SENSITIVE — copy exactly from schema

# Reasoning Process (internal, do NOT output)
1. Identify intent: trend / ranking / aggregate / funnel / filter?
2. Choose table: preference ADS > DWS > DWD
3. Choose columns matching the user's intent
4. Determine dt filter and any WHERE conditions
5. Determine GROUP BY / ORDER BY / LIMIT
6. Write the SQL

# Output Format — STRICT
Respond with EXACTLY one line containing only the SQL query.
No markdown code blocks, no explanations, no "Here is the SQL".
IF the question cannot be answered with available data, respond: UNABLE_TO_ANSWER

# Edge Cases
- "最近N天" / "近N天" → dt BETWEEN '2014-12-{19-N}' AND '2014-12-18'
- No date specified → default dt='2014-12-18'
- Question is not about data analysis → respond UNABLE_TO_ANSWER
- Metric or column doesn't exist → respond UNABLE_TO_ANSWER"""


# ============================================================
# FEW-SHOT BANK — 按问题类型索引（动态匹配 2-3 条示例）
# ============================================================

FEWSHOT_BANK = {
    "trend": {
        "keywords": ["趋势", "变化", "走势", "每天", "逐日", "近N天", "最近7天", "7天", "几天"],
        "examples": [
            {
                "q": "最近7天的DAU趋势",
                "sql": "SELECT dt, total_uv AS dau FROM dws_platform_day WHERE dt BETWEEN '2014-12-12' AND '2014-12-18' ORDER BY dt;",
            },
            {
                "q": "最近7天每天订单量变化",
                "sql": "SELECT dt, total_buy AS orders FROM dws_platform_day WHERE dt BETWEEN '2014-12-12' AND '2014-12-18' ORDER BY dt;",
            },
        ],
    },
    "ranking": {
        "keywords": ["最高", "最低", "热门", "排行", "排名", "前N", "Top", "top", "topN", "哪些"],
        "examples": [
            {
                "q": "购买量最高的10个类目",
                "sql": "SELECT item_category, SUM(buy_cnt) AS total_buy FROM ads_category_topn WHERE dt='2014-12-18' GROUP BY item_category ORDER BY total_buy DESC LIMIT 10;",
            },
            {
                "q": "浏览量最高的5个商品",
                "sql": "SELECT item_id, SUM(pv_cnt) AS total_pv FROM dws_item_day WHERE dt='2014-12-18' GROUP BY item_id ORDER BY total_pv DESC LIMIT 5;",
            },
            {
                "q": "转化率最低的3个类目",
                "sql": "SELECT item_category, buy_conversion FROM ads_category_topn WHERE dt='2014-12-18' ORDER BY buy_conversion ASC LIMIT 3;",
            },
        ],
    },
    "aggregate": {
        "keywords": ["多少", "总数", "总量", "统计", "汇总", "平均", "人均", "占比"],
        "examples": [
            {
                "q": "12月18日有多少活跃用户",
                "sql": "SELECT total_uv AS active_users FROM dws_platform_day WHERE dt='2014-12-18';",
            },
            {
                "q": "昨天总订单量是多少",
                "sql": "SELECT total_orders FROM ads_daily_kpi WHERE dt='2014-12-18';",
            },
            {
                "q": "12月的人均PV是多少",
                "sql": "SELECT avg_pv FROM ads_daily_kpi WHERE dt='2014-12-18';",
            },
        ],
    },
    "funnel": {
        "keywords": ["漏斗", "转化", "转化率", "流转", "环节"],
        "examples": [
            {
                "q": "12月18日的全站转化漏斗",
                "sql": "SELECT level_name, pv_users, fav_users, cart_users, buy_users FROM ads_funnel WHERE dt='2014-12-18' AND item_category IS NULL;",
            },
            {
                "q": "品类4245的转化漏斗数据",
                "sql": "SELECT * FROM ads_funnel WHERE dt='2014-12-18' AND item_category=4245;",
            },
        ],
    },
    "filter": {
        "keywords": ["品类", "类目", "商品ID", "用户ID", "某个", "特定", "什么品类", "哪个类目"],
        "examples": [
            {
                "q": "品类4245最近3天每天的购买量",
                "sql": "SELECT dt, buy_cnt FROM dws_category_day WHERE item_category=4245 AND dt BETWEEN '2014-12-16' AND '2014-12-18' ORDER BY dt;",
            },
            {
                "q": "商品ID为232431562的浏览量是多少",
                "sql": "SELECT SUM(pv_cnt) AS total_pv FROM dws_item_day WHERE item_id=232431562 AND dt='2014-12-18';",
            },
            {
                "q": "用户98047837最近都买了什么",
                "sql": "SELECT item_id, item_category FROM dwd_user_behavior WHERE user_id=98047837 AND behavior_type=4 AND dt BETWEEN '2014-11-18' AND '2014-12-18';",
            },
        ],
    },
    "kpi": {
        "keywords": ["KPI", "kpi", "指标", "概览", "今日数据", "核心数据", "大盘", "整体"],
        "examples": [
            {
                "q": "12月18日的核心指标",
                "sql": "SELECT dau, total_pv, total_orders, buy_conversion, avg_pv FROM ads_daily_kpi WHERE dt='2014-12-18';",
            },
        ],
    },
}


def _match_examples(question: str, max_examples: int = 3) -> List[dict]:
    """根据问题关键词匹配最相关的 Few-shot 示例"""
    scored = []
    for category, entry in FEWSHOT_BANK.items():
        score = 0
        for kw in entry["keywords"]:
            if kw.lower() in question.lower():
                score += 1
        if score > 0:
            scored.append((score, entry["examples"]))

    scored.sort(key=lambda x: x[0], reverse=True)

    examples = []
    seen = set()
    for _, batch in scored:
        for ex in batch:
            if ex["q"] not in seen and len(examples) < max_examples:
                examples.append(ex)
                seen.add(ex["q"])
        if len(examples) >= max_examples:
            break

    # 兜底：如果没有匹配到，用 aggregate + ranking 的示例
    if not examples:
        examples = [
            FEWSHOT_BANK["aggregate"]["examples"][0],
            FEWSHOT_BANK["ranking"]["examples"][0],
        ]

    logger.debug("Matched %d few-shot examples for: '%s'", len(examples), question[:50])
    return examples[:max_examples]


def _format_fewshot(examples: List[dict]) -> str:
    """将示例格式化为 Prompt 文本"""
    lines = []
    for i, ex in enumerate(examples, 1):
        lines.append(f"Example {i}:")
        lines.append(f"  Q: {ex['q']}")
        lines.append(f"  A: {ex['sql']}")
        lines.append("")
    return "\n".join(lines)


# ============================================================
# 4. COT — 推理引导
# ============================================================

def _build_system_prompt() -> str:
    return SYSTEM_PROMPT


def _build_user_prompt(question: str, schema_text: str) -> str:
    """组装 User Prompt：Schema + 动态 Few-shot + 问题"""
    examples = _match_examples(question)
    fewshot_text = _format_fewshot(examples)

    return f"""{schema_text}

---
## Examples (for reference)

{fewshot_text}
---
## Task

User Question: {question}

Generate SQL:"""


# ============================================================
# SQL 清理
# ============================================================

def _clean_sql(raw: str) -> str:
    """从 LLM 返回值中提取纯净 SQL"""
    sql = raw.strip()

    # 检测 UNABLE_TO_ANSWER
    if sql.upper().startswith("UNABLE_TO_ANSWER"):
        return "UNABLE_TO_ANSWER"

    # 去掉 markdown 代码块
    m = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", sql, re.DOTALL)
    if m:
        sql = m.group(1).strip()

    # 找第一个 SQL 关键字
    for kw in ["SELECT", "WITH", "INSERT", "SHOW", "DESC"]:
        idx = sql.upper().find(kw)
        if idx >= 0:
            sql = sql[idx:]
            break

    # 截断到最后一个分号
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
        question:    "最近3天购买量最高的5个类目"
        schema_text: 自定义 Schema（不传则自动构建）
        model:       模型名（如 "qwen-max"）

    Returns:
        {"sql": "SELECT ...", "raw": "LLM原始返回"}
    """
    llm = get_llm_client()

    if schema_text is None:
        schema_text = get_schema_text()

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(question, schema_text)

    logger.debug("System prompt: %d chars, User prompt: %d chars",
                 len(system_prompt), len(user_prompt))

    raw = llm.chat(prompt=user_prompt, system_prompt=system_prompt, temperature=0.05)
    sql = _clean_sql(raw)

    logger.info("Q: %s", question[:80])
    logger.info("SQL: %s", sql[:200])

    return {"sql": sql, "raw": raw}


# ============================================================
# 命令行测试
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    test_questions = [
        # aggregate
        "12月18日有多少活跃用户？",
        # trend
        "最近7天的DAU趋势",
        # ranking
        "购买量最高的10个类目",
        # funnel
        "12月18日的全站转化漏斗数据",
        # filter
        "品类4245最近3天的购买量",
        # edge
        "今天天气怎么样",
    ]

    print(f"\n{'='*60}")
    print("NL2SQL Generator — Standard Prompt Engineering")
    print(f"{'='*60}")

    for q in test_questions:
        result = generate_sql(q)
        print(f"\nQ: {q}")
        print(f"SQL: {result['sql']}")
