import duckdb
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ecommerce.duckdb')
DB_PATH = os.path.abspath(DB_PATH)

print(f"DB path: {DB_PATH}")
print(f"DB exists: {os.path.exists(DB_PATH)}")

if not os.path.exists(DB_PATH):
    print("DB file not found!")
    exit(1)

conn = duckdb.connect(DB_PATH)
tables = [
    'dwd_user_behavior',
    'dws_platform_day',
    'dws_item_day',
    'dws_category_day',
    'ads_daily_kpi',
    'ads_funnel',
    'ads_user_rfm',
    'ads_user_recommend',
]

for t in tables:
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  [OK] {t:30s} {cnt:>8,} rows")
    except Exception as e:
        print(f"  [FAIL] {t:30s} {e}")

conn.close()
print("Done!")
