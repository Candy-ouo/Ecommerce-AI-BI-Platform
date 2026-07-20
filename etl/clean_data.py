"""
clean_data.py
=============
数据清洗脚本：在 1 万条样本上开发调试，通过后交 A 对全量 1225 万行运行。

清洗逻辑：
  1. 用户行为表：
     - time 拆分为 behavior_date (YYYY-MM-DD) + behavior_hour (0-23)
     - behavior_type 数字 → 中文映射 (新增 behavior_type_cn 列)
     - 过滤无效 behavior_type 和异常时间范围
     - 去重
     - geohash 保留原值（空值保持为空）
  2. 商品信息表：
     - 按 item_id 去重（48万行 → ~31万行）
     - geohash 保留原值

产出：
  - data/processed/user_behavior_clean.csv
  - data/processed/item_info_clean.csv

用法：
  # 开发模式（在 1 万条样本上跑）
  python etl/clean_data.py --user data/sample/sample_10k.csv --mode dev

  # 全量模式（A 在自己机器上跑）
  python etl/clean_data.py --mode full

  # 指定自定义路径
  python etl/clean_data.py --user path/to/user.csv --item path/to/item.csv --out-user path/to/out1.csv --out-item path/to/out2.csv
"""

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd

# ============================================================
# 常量
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 默认路径
DEFAULT_USER_CSV = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_user.csv"
DEFAULT_ITEM_CSV = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_item.csv"
DEFAULT_OUT_USER = PROJECT_ROOT / "data" / "processed" / "user_behavior_clean.csv"
DEFAULT_OUT_ITEM = PROJECT_ROOT / "data" / "processed" / "item_info_clean.csv"
# dev 模式下从原始 CSV 读取的前 N 行（用于开发调试）
DEV_SAMPLE_ROWS = 10_000

# 行为类型映射
BEHAVIOR_MAP = {
    1: "浏览",
    2: "收藏",
    3: "加购",
    4: "购买",
}
VALID_BEHAVIOR_TYPES = set(BEHAVIOR_MAP.keys())

# 时间范围（数据说明：2014-11-18 ~ 2014-12-18，精确到小时）
DATE_MIN = pd.Timestamp("2014-11-18 00")
DATE_MAX = pd.Timestamp("2014-12-18 23")

# 分块大小（全量模式使用）
CHUNKSIZE = 100_000

# 输出列（依照 DEV_PLAN 4.4 契约）
USER_OUTPUT_COLUMNS = [
    "user_id",
    "item_id",
    "behavior_type",
    "behavior_type_cn",
    "user_geohash",
    "item_category",
    "behavior_date",
    "behavior_hour",
]

ITEM_OUTPUT_COLUMNS = [
    "item_id",
    "item_geohash",
    "item_category",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="数据清洗脚本 — 用户行为表 + 商品信息表"
    )
    parser.add_argument(
        "--mode", choices=["dev", "full"], default="dev",
        help="dev: 在 1 万条样本上运行; full: 全量 1225 万行 (默认: dev)"
    )
    parser.add_argument("--user", type=str, help="用户行为表 CSV 路径")
    parser.add_argument("--item", type=str, help="商品信息表 CSV 路径")
    parser.add_argument("--out-user", type=str, help="清洗后用户行为表输出路径")
    parser.add_argument("--out-item", type=str, help="清洗后商品信息表输出路径")
    parser.add_argument("--chunksize", type=int, default=CHUNKSIZE,
                        help=f"分块读取行数 (默认: {CHUNKSIZE:,})")
    return parser.parse_args()


# ============================================================
# 商品信息表清洗（小表，全量加载）
# ============================================================

def clean_item_table(item_path: Path) -> pd.DataFrame:
    """
    商品信息表清洗：
      1. 读取 CSV
      2. 按 item_id 去重（保留首次出现）
      3. 输出清洗统计
    """
    print(f"\n{'─' * 50}")
    print(f"  清洗商品信息表")
    print(f"{'─' * 50}")
    print(f"  读取: {item_path}")

    df = pd.read_csv(item_path, dtype=str)
    rows_before = len(df)
    unique_before = df["item_id"].nunique()
    print(f"  原始行数: {rows_before:,}")
    print(f"  去重 item_id 数: {unique_before:,}")

    # 按 item_id 去重，保留第一次出现
    df = df.drop_duplicates(subset="item_id", keep="first")
    rows_after = len(df)
    duplicates = rows_before - rows_after
    print(f"  去重后行数: {rows_after:,} (移除 {duplicates:,} 条重复)")

    # 对齐输出列
    df = df[ITEM_OUTPUT_COLUMNS]

    # 检查 item_category 是否还有重复的 item_id 映射到不同 category
    dup_check = df.groupby("item_id")["item_category"].nunique()
    multi_cat = dup_check[dup_check > 1]
    if len(multi_cat) > 0:
        print(f"  [WARN] {len(multi_cat)} 个 item_id 仍映射到多个 category（保留首次出现）")

    # 空值统计
    geo_empty = (df["item_geohash"].isna() | (df["item_geohash"] == "")).sum()
    geo_empty_pct = geo_empty / rows_after * 100
    print(f"  item_geohash 空值率: {geo_empty:,}/{rows_after:,} ({geo_empty_pct:.1f}%)")

    return df


# ============================================================
# 用户行为表清洗（大表，分块处理）
# ============================================================

def clean_user_behavior_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """
    对单块数据执行清洗逻辑（不涉及全局去重）。
    返回清洗后的 DataFrame。
    """
    # 1. 过滤无效 behavior_type
    chunk["behavior_type_int"] = pd.to_numeric(chunk["behavior_type"], errors="coerce")
    valid_mask = chunk["behavior_type_int"].isin(VALID_BEHAVIOR_TYPES)
    invalid_count = (~valid_mask).sum()
    chunk = chunk[valid_mask].copy()

    # 2. 解析时间字段
    chunk["time_dt"] = pd.to_datetime(chunk["time"], format="%Y-%m-%d %H", errors="coerce")
    time_valid = chunk["time_dt"].notna()
    invalid_time_count = (~time_valid).sum()
    chunk = chunk[time_valid].copy()

    # 3. 过滤异常时间范围
    in_range = (chunk["time_dt"] >= DATE_MIN) & (chunk["time_dt"] <= DATE_MAX)
    out_of_range_count = (~in_range).sum()
    chunk = chunk[in_range].copy()

    # 4. 拆分时间
    chunk["behavior_date"] = chunk["time_dt"].dt.strftime("%Y-%m-%d")
    chunk["behavior_hour"] = chunk["time_dt"].dt.hour.astype(int)

    # 5. 行为类型中文映射
    chunk["behavior_type_cn"] = chunk["behavior_type_int"].map(BEHAVIOR_MAP)

    # 6. behavior_type 转回字符串（保留原始值）
    chunk["behavior_type"] = chunk["behavior_type_int"].astype(str)

    # 7. geohash 保留原值（空值保持为空字符串）
    chunk["user_geohash"] = chunk["user_geohash"].fillna("")

    # 8. item_category 保留原值
    chunk["item_category"] = chunk["item_category"].fillna("")

    # 返回统计
    stats = {
        "invalid_behavior": invalid_count,
        "invalid_time": invalid_time_count,
        "out_of_range": out_of_range_count,
    }

    return chunk[USER_OUTPUT_COLUMNS], stats


def clean_user_table(user_path: Path, chunksize: int, nrows: int = None) -> pd.DataFrame:
    """
    用户行为表清洗（小文件 / dev 模式全量读入）。

    对大文件请使用 clean_user_table_chunked()。
    """
    print(f"\n{'─' * 50}")
    print(f"  清洗用户行为表")
    print(f"{'─' * 50}")
    print(f"  读取: {user_path}")
    if nrows:
        print(f"  限制行数: {nrows:,} (dev 模式)")
    print(f"  输出列: {USER_OUTPUT_COLUMNS}")

    start_time = time.time()

    df = pd.read_csv(user_path, dtype=str, nrows=nrows)
    total_rows = len(df)
    df, stats = clean_user_behavior_chunk(df)
    total_kept = len(df)

    elapsed = time.time() - start_time
    total_errors = stats["invalid_behavior"] + stats["invalid_time"] + stats["out_of_range"]
    print(f"\n  清洗统计:")
    print(f"    输入行数:     {total_rows:>12,}")
    print(f"    输出行数:     {total_kept:>12,}")
    print(f"    过滤-无效行为: {stats['invalid_behavior']:>12,}")
    print(f"    过滤-时间异常: {stats['invalid_time']:>12,}")
    print(f"    过滤-日期越界: {stats['out_of_range']:>12,}")
    print(f"    总过滤:       {total_errors:>12,}")
    print(f"    清洗耗时:     {elapsed:>11.1f}s")

    # 行为类型分布
    if total_kept > 0:
        print(f"\n  清洗后行为类型分布:")
        dist = df["behavior_type_cn"].value_counts()
        for k, v in dist.items():
            print(f"    {k}: {v:>8,} ({v/total_kept*100:.1f}%)")

    return df


def clean_user_table_chunked(user_path: Path, out_path: Path, chunksize: int):
    """
    全量分块清洗：逐块读取 → 清洗 → 追加写入 CSV。
    避免内存溢出，支持 400MB+ 文件。
    """
    print(f"\n{'─' * 50}")
    print(f"  清洗用户行为表（全量分块模式）")
    print(f"{'─' * 50}")
    print(f"  读取: {user_path}")
    print(f"  分块大小: {chunksize:,} 行/块")

    file_size_mb = os.path.getsize(user_path) / (1024 * 1024)
    print(f"  文件大小: {file_size_mb:.1f} MB")

    total_rows = 0
    total_kept = 0
    total_errors = 0
    start_time = time.time()
    first_chunk = True

    os.makedirs(out_path.parent, exist_ok=True)

    # 逐块读取并清洗
    reader = pd.read_csv(user_path, dtype=str, chunksize=chunksize)
    chunk_count = 0

    for chunk in reader:
        chunk_count += 1
        rows_before = len(chunk)
        total_rows += rows_before

        cleaned, stats = clean_user_behavior_chunk(chunk)
        rows_after = len(cleaned)
        total_kept += rows_after
        total_errors += stats["invalid_behavior"] + stats["invalid_time"] + stats["out_of_range"]

        # 写入文件（第一块写 header，后续追加不写 header）
        write_mode = "w" if first_chunk else "a"
        header = first_chunk
        cleaned.to_csv(out_path, mode=write_mode, header=header, index=False)
        first_chunk = False

        # 进度日志（每 10 块输出一次）
        if chunk_count % 10 == 0:
            elapsed = time.time() - start_time
            speed = total_rows / elapsed if elapsed > 0 else 0
            print(f"  [进度] 已处理 {chunk_count} 块, "
                  f"{total_rows:>10,} 行, "
                  f"保留 {total_kept:>10,} 行, "
                  f"{speed:>.0f} 行/s")

    elapsed = time.time() - start_time
    print(f"\n  清洗统计:")
    print(f"    输入行数:     {total_rows:>12,}")
    print(f"    输出行数:     {total_kept:>12,}")
    print(f"    过滤异常行:   {total_errors:>12,}")
    print(f"    总块数:       {chunk_count:>12,}")
    print(f"    清洗耗时:     {elapsed:>11.1f}s")
    if total_rows > 0:
        print(f"    处理速度:     {total_rows/elapsed:>11.0f} 行/s")

    # 行为类型分布
    print(f"\n  行为类型分布 (输出数据):")
    # 快速统计：重新读一遍输出文件的前几百块
    sample_df = pd.read_csv(out_path, nrows=100000)
    if "behavior_type_cn" in sample_df.columns:
        dist = sample_df["behavior_type_cn"].value_counts()
        for k, v in dist.items():
            print(f"    {k}: {v:>8,}")
        print(f"    (基于前 {len(sample_df):,} 行采样)")


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("  clean_data.py — 数据清洗")
    print("=" * 60)

    args = parse_args()

    # 确定输入路径
    if args.mode == "dev":
        user_path = Path(args.user) if args.user else DEFAULT_USER_CSV
        # dev 模式下也处理商品表（小文件全量加载即可）
        item_path = Path(args.item) if args.item else DEFAULT_ITEM_CSV
        print(f"  [DEV 模式] 读取原始 CSV 前 {DEV_SAMPLE_ROWS:,} 行进行开发调试")
    else:
        user_path = Path(args.user) if args.user else DEFAULT_USER_CSV
        item_path = Path(args.item) if args.item else DEFAULT_ITEM_CSV
        print(f"  [FULL 模式] 全量数据")

    out_user = Path(args.out_user) if args.out_user else DEFAULT_OUT_USER
    out_item = Path(args.out_item) if args.out_item else DEFAULT_OUT_ITEM

    # 验证输入文件
    if not user_path.exists():
        print(f"[ERROR] 用户行为表不存在: {user_path}")
        sys.exit(1)
    if item_path and not item_path.exists():
        print(f"[ERROR] 商品信息表不存在: {item_path}")
        sys.exit(1)

    # ---- 清洗商品信息表 ----
    if item_path:
        item_df = clean_item_table(item_path)
        os.makedirs(out_item.parent, exist_ok=True)
        item_df.to_csv(out_item, index=False, encoding="utf-8")
        print(f"  已输出: {out_item} ({len(item_df):,} 行)")
    else:
        print(f"\n  [SKIP] 商品信息表 — DEV 模式不需要单独清洗")

    # ---- 清洗用户行为表 ----
    if args.mode == "dev":
        # 开发模式：只读前 N 行来验证清洗逻辑
        df = clean_user_table(user_path, args.chunksize, nrows=DEV_SAMPLE_ROWS)
        os.makedirs(out_user.parent, exist_ok=True)
        df.to_csv(out_user, index=False, encoding="utf-8")
        print(f"\n  已输出: {out_user} ({len(df):,} 行)")
    else:
        # 全量模式：分块流式处理
        clean_user_table_chunked(user_path, out_user, args.chunksize)
        print(f"\n  已输出: {out_user}")

    print(f"\n{'=' * 60}")
    print(f"  全部清洗完成！")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
