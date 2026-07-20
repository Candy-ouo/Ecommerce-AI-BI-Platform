"""
查询结果智能解读

将 SQL 查询结果（DataFrame）转换为自然语言回答，让业务人员不用看表格也能理解数据。

使用方式（C 在 chat.py 中这样调用）：
    from ai.nl2sql.result_explainer import explain_result
    answer = explain_result(question, sql, df)
    # → "12月18日共有 8,230 名活跃用户，较前一日增长 1.6%..."
"""

import sys
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from ai.llm_client import get_llm_client

logger = logging.getLogger(__name__)

# ============================================================
# Prompt
# ============================================================

SYSTEM_PROMPT = """# Role
You are a professional e-commerce data analyst. Your job is to explain SQL query results in plain, natural Chinese that anyone can understand.

# Context
Data period: 2014-11-18 to 2014-12-18 (31 days). Reference dates naturally when relevant.

# Output Format
1. Answer in Chinese, friendly and professional.
2. Summarize key numbers first, then provide context or trends.
3. Multiple rows: mention top items and overall patterns.
4. Empty result: explain what that means (e.g., "该日期暂无数据").
5. Concise: 2-5 sentences is usually enough.
6. Format large numbers with commas or 万 as appropriate.

# Constraints
- Do NOT repeat the SQL or show raw data table.
- Do NOT fabricate numbers not in the data.
- If the data looks unusual, briefly flag it (e.g., "该数据可能有异常，建议进一步核实")."""


# ============================================================
# 格式化
# ============================================================

def _format_result(df: pd.DataFrame, max_rows: int = 20) -> str:
    """将 DataFrame 格式化为 LLM 可读的文本表格"""
    if df is None or df.empty:
        return "(empty result - no data returned)"

    # 限制行数
    display_df = df.head(max_rows)
    n_total = len(df)

    lines = []
    lines.append(f"Query returned {n_total} row(s):")
    lines.append("")

    # 列名
    lines.append(" | ".join(display_df.columns.astype(str)))
    lines.append("-" * len(lines[-1]))

    # 数据行
    for _, row in display_df.iterrows():
        vals = [str(v)[:50] for v in row.values]  # 截断长文本
        lines.append(" | ".join(vals))

    if n_total > max_rows:
        lines.append(f"... ({n_total - max_rows} more rows not shown)")

    return "\n".join(lines)


# ============================================================
# 公共接口
# ============================================================

def explain_result(
    question: str,
    sql: str,
    result_df: pd.DataFrame,
    temperature: float = 0.3,
) -> str:
    """
    将查询结果转为自然语言解读。

    Args:
        question:   用户的原始自然语言问题
        sql:        生成的 SQL 语句
        result_df:  执行 SQL 返回的 Pandas DataFrame
        temperature: LLM 温度（0.3 兼顾准确性和多样性）

    Returns:
        自然语言解读文本

    Example:
        >>> explain_result("最近3天购买量最高的品类",
        ...                "SELECT ...",
        ...                df)  # df有10行数据
        "近3天购买量最高的品类是ID 4245（2,800次购买），
         其次是ID 8270（2,100次），ID 5894（1,950次）。
         前三个品类占Top10总购买量的45%，建议重点关注。"
    """
    llm = get_llm_client()
    result_text = _format_result(result_df)

    user_prompt = f"""User asked: "{question}"

The system generated this SQL:
```
{sql}
```

The query returned these results:
```
{result_text}
```

Please explain these results in natural Chinese for the user:"""

    explanation = llm.chat(
        prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=temperature,
    )

    logger.info("Explained result: question='%s', result_rows=%d, response_len=%d",
                question[:60], len(result_df), len(explanation))

    return explanation


# ============================================================
# 命令行测试
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    # 模拟一组查询结果
    mock_df = pd.DataFrame({
        "item_category": [4245, 8270, 5894, 10703, 1863],
        "buy_cnt": [2800, 2100, 1950, 1600, 1200],
    })

    question = "最近3天购买量最高的5个类目"
    sql = "SELECT item_category, SUM(buy_cnt) AS buy_cnt FROM dws_category_day WHERE dt BETWEEN '2014-12-16' AND '2014-12-18' GROUP BY item_category ORDER BY buy_cnt DESC LIMIT 5"

    print(f"Q: {question}")
    print(f"SQL: {sql}")
    print(f"\nData:\n{mock_df}\n")
    print("Explanation:")
    print(explain_result(question, sql, mock_df))
