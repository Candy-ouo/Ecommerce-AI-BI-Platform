"""命令行 AI 对话 Demo — NL2SQL → Hive执行 → AI解读 完整链路"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from ai.nl2sql.sql_generator import smart_chat
from ai.nl2sql.result_explainer import explain_result

# 尝试连 Hive
_executor = None
try:
    from pyhive import hive
    _conn = hive.Connection(host='localhost', port=10000, database='ecommerce_bi', auth='NONE')
    def _run_sql(sql):
        return pd.read_sql(sql.rstrip(';'), _conn)
    _executor = _run_sql
    print("[OK] Hive connected — SQL will be executed with real data")
except Exception as e:
    print("[WARN] Hive not available — will show SQL only")
    print(f"  {e}")

print("=" * 55)
print("  AI 电商分析助手 — 完整链路 Demo")
print("=" * 55)
print("  数据查询:  NL → SQL → Hive执行 → AI解读")
print("  知识问答:  运营建议、行业知识")
print("  闲聊对话:  问候、介绍")
print("=" * 55)
print("  试试: 最近7天DAU趋势 | 转化率低怎么优化 | 你好")
print("=" * 55)

while True:
    user_input = input("\nYou: ").strip()
    if not user_input:
        continue
    if user_input.lower() in ("quit", "exit", "q"):
        print("Bye!")
        break

    result = smart_chat(user_input)

    if result["type"] == "data_query":
        sql = result["sql"]
        print(f"\n[SQL] {sql}")

        if sql == "UNABLE_TO_ANSWER":
            print("[结果] 无法回答此问题")
            continue

        if _executor:
            try:
                df = _executor(sql)
                print(f"[结果] {len(df)} 行数据")
                print(df.to_string(max_rows=8))
                print()
                print(explain_result(user_input, sql, df))
            except Exception as e:
                print(f"[执行失败] {e}")
        else:
            print("(Hive 未连接，SQL 已生成但未执行)")

    elif result["type"] == "off_topic":
        print(f"\n{result['answer']}")

    else:
        mode = "闲聊" if result["type"] == "general_chat" else "知识问答"
        print(f"\n[{mode}] {result['answer']}")
