"""测试意图分类 + NL2SQL 是否正常"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

from ai.nl2sql.sql_generator import smart_chat, generate_sql

# 测试意图分类
print("=" * 60)
print("1. smart_chat intent test")
print("=" * 60)
result = smart_chat("销量最高的商品是什么")
print(f"Type: {result.get('type')}")
print(f"SQL: {result.get('sql', 'N/A')[:200] if result.get('sql') else 'N/A'}")
print(f"Answer: {result.get('answer', 'N/A')[:200] if result.get('answer') else 'N/A'}")

print()
print("=" * 60)
print("2. generate_sql test")
print("=" * 60)
result2 = generate_sql("销量最高的商品是什么")
print(f"SQL: {result2.get('sql', 'N/A')[:300]}")
