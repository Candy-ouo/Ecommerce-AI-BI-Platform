"""统一 SQL 查询封装（所有 API 共用）。

团队决策用 Hive（pyhive 连接）。DB_ENGINE=duckdb 时走本地 DuckDB 兜底，
仅供无 Hive 环境的本地开发调试，接口契约不变。
"""
import pandas as pd

from config import (
    DB_ENGINE, DUCKDB_PATH,
    HIVE_HOST, HIVE_PORT, HIVE_USER, HIVE_PASSWORD, HIVE_DATABASE,
)

_duckdb_conn = None


def _get_duckdb_conn():
    global _duckdb_conn
    if _duckdb_conn is None:
        import duckdb
        _duckdb_conn = duckdb.connect(DUCKDB_PATH)
    return _duckdb_conn


def query(sql: str) -> pd.DataFrame:
    """执行 SQL，返回 DataFrame。Hive 模式下通过 pyhive 连接。"""
    if DB_ENGINE == "duckdb":
        return _get_duckdb_conn().execute(sql).fetchdf()

    from pyhive import hive
    conn = hive.Connection(
        host=HIVE_HOST,
        port=HIVE_PORT,
        username=HIVE_USER,
        password=HIVE_PASSWORD,
        database=HIVE_DATABASE,
    )
    try:
        return pd.read_sql(sql, conn)
    finally:
        conn.close()
