"""
Schema 上下文构建器

读取 docs/schema.md → 解析表名/字段/类型/说明 → 生成 LLM Prompt 用的结构化 Schema 文本。
NL2SQL 的 sql_generator.py 依赖本模块提供的 schema 上下文。

解析结果示例：
    {
      "dws_category_day": {
        "comment": "类目日粒度指标",
        "partition": "dt (YYYY-MM-DD)",
        "columns": [
          {"name": "item_category", "type": "BIGINT", "comment": "类目ID"},
          {"name": "pv_cnt", "type": "BIGINT", "comment": "当日浏览量"},
          ...
        ]
      },
      ...
    }
"""

import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "Docs" / "schema.md"


# ============================================================
# 解析器
# ============================================================

# ============================================================
# 解析辅助
# ============================================================

def _parse_table_rows(table_info: dict, lines: list, start: int):
    """解析从 start 行开始的单个 markdown 表格，填充到 table_info['columns']"""
    i = start
    while i < len(lines):
        row = lines[i].strip()
        # 表格结束：空行、新标题、或非表格行
        if not row:
            i += 1
            continue
        if not row.startswith("|"):
            break
        if row.startswith("|---") or row.startswith("| ---"):
            i += 1
            continue

        cells = [c.strip() for c in row.split("|")[1:-1]]

        # 跳过表头行（"字段 | 类型 | 说明"）
        if cells and cells[0] in ("字段", "列名", "Column", "Field"):
            i += 1
            continue

        if len(cells) >= 3:
            table_info["columns"].append({
                "name": cells[0],
                "type": cells[1],
                "comment": cells[2],
            })
        i += 1


def _parse_schema_file(filepath: Path) -> dict:
    """
    解析 schema.md，返回 {table_name: table_info} 字典。
    适配当前 schema.md 的结构。
    """
    if not filepath.exists():
        raise FileNotFoundError(f"Schema file not found: {filepath}")

    text = filepath.read_text(encoding="utf-8")

    tables = {}
    current_table = None

    # 正则：匹配 "### X.X table_name — description" 或 "### X.X table_name" 或 "### X.X table_name（...）"
    table_header = re.compile(r"^###\s+\d+\.\d+\s+(\w+)\s*[—\-（(]?(.*)")

    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # 检测表头
        m = table_header.match(line)
        if m:
            table_name = m.group(1)
            comment = m.group(2).strip().rstrip("）)").strip() if m.group(2) else ""
            current_table = table_name
            tables[current_table] = {
                "comment": comment,
                "partition": None,
                "columns": [],
            }

            i += 1

            # 向后扫描，找第一个 markdown 表格（列定义表）
            while i < len(lines):
                row = lines[i].strip()
                if row.startswith("|") and "---" not in row:
                    # 找到表格，解析
                    break
                i += 1

            # 解析当前表格的所有行
            _parse_table_rows(tables[current_table], lines, i)
            continue

        i += 1

    # 手动补充分区信息（从已知的表结构）
    partitioned = {
        "ods_user_behavior", "dwd_user_behavior",
        "dws_user_day", "dws_item_day", "dws_category_day", "dws_platform_day",
        "ads_daily_kpi", "ads_funnel", "ads_category_topn", "ads_user_rfm",
    }
    for tname in tables:
        if tname in partitioned:
            tables[tname]["partition"] = "dt (格式 YYYY-MM-DD，如 2014-12-18)"

    logger.info("Parsed %d tables from schema.md", len(tables))
    return tables


# ============================================================
# Schema 文本构建
# ============================================================

def build_schema_text(tables: dict) -> str:
    """
    将解析后的表结构转为 LLM Prompt 友好的文本。
    格式简洁，节省 token。
    """
    lines = []
    lines.append("=" * 50)
    lines.append("DATABASE SCHEMA")
    lines.append("=" * 50)
    lines.append("")

    # 重要规则放在最前面
    lines.append("CRITICAL RULES:")
    lines.append("1. ALL queries MUST include a dt partition filter (WHERE dt = 'YYYY-MM-DD' or BETWEEN)")
    lines.append("2. Data range: 2014-11-18 to 2014-12-18 (31 days)")
    lines.append("3. behavior_type: 1=browse(浏览), 2=fav(收藏), 3=cart(加购), 4=buy(购买)")
    lines.append("4. Use Hive SQL syntax")
    lines.append("5. Return ONLY the SQL, no markdown wrapping, no explanation")
    lines.append("")

    # 按层级分组
    ods = [(n, t) for n, t in tables.items() if n.startswith("ods")]
    dwd = [(n, t) for n, t in tables.items() if n.startswith("dwd") or n.startswith("dim")]
    dws = [(n, t) for n, t in tables.items() if n.startswith("dws")]
    ads = [(n, t) for n, t in tables.items() if n.startswith("ads")]

    for group_name, group_tables in [
        ("ODS (原始数据层)", ods),
        ("DWD (明细 + 维度层)", dwd),
        ("DWS (日粒度汇总层 — NL2SQL 最常用)", dws),
        ("ADS (应用层 — 直接查询)", ads),
    ]:
        if not group_tables:
            continue
        lines.append(f"--- {group_name} ---")
        for tname, tinfo in group_tables:
            comment_str = f" -- {tinfo['comment']}" if tinfo["comment"] else ""
            partition_str = f" [PARTITION: {tinfo['partition']}]" if tinfo["partition"] else ""
            lines.append(f"\nTABLE: {tname}{comment_str}{partition_str}")

            col_strs = []
            for col in tinfo["columns"]:
                col_strs.append(f"  {col['name']} ({col['type']}) -- {col['comment']}")
            lines.extend(col_strs)

        lines.append("")

    # 查询示例
    lines.append("--- QUERY EXAMPLES ---")
    lines.append("")
    lines.append("Q: '最近7天的DAU趋势'")
    lines.append("A: SELECT dt, total_uv AS dau FROM dws_platform_day WHERE dt BETWEEN '2014-12-12' AND '2014-12-18' ORDER BY dt")
    lines.append("")
    lines.append("Q: '12月18日购买量最高的5个类目'")
    lines.append("A: SELECT item_category, buy_cnt FROM ads_category_topn WHERE dt='2014-12-18' ORDER BY buy_cnt DESC LIMIT 5")
    lines.append("")
    lines.append("Q: '品类4245的转化漏斗'")
    lines.append("A: SELECT * FROM ads_funnel WHERE dt='2014-12-18' AND item_category=4245")
    lines.append("")
    lines.append("Q: '12月18日总订单量'")
    lines.append("A: SELECT total_orders FROM ads_daily_kpi WHERE dt='2014-12-18'")

    return "\n".join(lines)


# ============================================================
# 公共接口
# ============================================================

# 缓存：只在首次调用时解析一次
_schema_cache: Optional[str] = None


def get_schema_text(filepath: str = None) -> str:
    """
    获取 LLM Prompt 用的 Schema 文本。
    首次调用时解析 schema.md，之后走缓存。

    Args:
        filepath: schema.md 路径（默认 Docs/schema.md）

    Returns:
        一段包含所有表结构、查询规则、示例的文本，可直接拼入 Prompt
    """
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache

    path = Path(filepath) if filepath else DEFAULT_SCHEMA_PATH
    tables = _parse_schema_file(path)
    _schema_cache = build_schema_text(tables)
    return _schema_cache


def get_tables(filepath: str = None) -> dict:
    """获取解析后的表结构字典（供其他模块直接使用）"""
    path = Path(filepath) if filepath else DEFAULT_SCHEMA_PATH
    return _parse_schema_file(path)


def reset_cache():
    """清空缓存（schema.md 更新后调用）"""
    global _schema_cache
    _schema_cache = None


# ============================================================
# 命令行：查看生成的 Schema 文本
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    text = get_schema_text()
    print(text)
