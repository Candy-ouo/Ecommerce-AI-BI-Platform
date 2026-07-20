"""
sample_extract.py
=================
从 1225 万行用户行为表中随机抽取 10,000 条记录，与商品信息表关联后，
输出 → data/sample/sample_10k.csv，供全员开发调试使用。

用法：
    python etl/sample_extract.py

依赖：仅标准库 + pandas（用于读取商品表和输出 CSV）
"""

import csv
import os
import random
import sys
from pathlib import Path

# 固定随机种子，保证每次抽样结果可复现
random.seed(42)

# 路径配置（相对于项目根目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

USER_CSV = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_user.csv"
ITEM_CSV = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_item.csv"
OUTPUT_CSV = PROJECT_ROOT / "data" / "sample" / "sample_10k.csv"

SAMPLE_SIZE = 10_000


def count_lines(filepath: Path) -> int:
    """快速统计文件总行数（含 header）。"""
    count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


def pick_line_numbers(total_lines: int, sample_size: int, header_line: int = 0) -> set:
    """
    从 [header_line+1, total_lines-1] 范围内随机抽取 sample_size 个行号。
    header_line=0 表示第 0 行是表头，数据行从第 1 行开始。
    """
    data_start = header_line + 1
    data_end = total_lines - 1
    chosen = random.sample(range(data_start, data_end + 1), sample_size)
    return set(chosen)


def extract_rows(filepath: Path, target_lines: set) -> list[dict]:
    """
    流式扫描 CSV，只保留行号在 target_lines 中的行。
    返回 list[dict]，每行是 dict（用 csv.DictReader 解析）。
    """
    result = []
    target_sorted = sorted(target_lines)
    target_idx = 0

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_idx, row in enumerate(reader, start=1):  # 数据行从第 1 行开始（跳过 header）
            if target_idx >= len(target_sorted):
                break
            if row_idx == target_sorted[target_idx]:
                result.append(row)
                target_idx += 1

    return result


def load_item_table(filepath: Path) -> dict:
    """
    读取商品信息表，返回 {item_id: (item_geohash, item_category)} 的字典。
    如有重复 item_id，保留第一次出现的记录并打印警告。
    """
    item_map = {}
    duplicate_count = 0

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            iid = row["item_id"]
            if iid in item_map:
                duplicate_count += 1
            else:
                item_map[iid] = (row["item_geohash"], row["item_category"])

    if duplicate_count:
        print(f"[WARN] 商品表中有 {duplicate_count} 条重复 item_id，已保留首次出现的记录")

    return item_map


def join_and_write(user_rows: list[dict], item_map: dict, output_path: Path):
    """将抽样行与商品表 JOIN，写入 CSV。"""
    matched = 0
    unmatched = 0

    os.makedirs(output_path.parent, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "user_id", "item_id", "behavior_type",
            "user_geohash", "user_item_category",  # 行为表中的 item_category
            "time",
            "item_geohash", "item_item_category",   # 商品表中的 item_category
        ])

        for row in user_rows:
            iid = row["item_id"]
            item_info = item_map.get(iid)

            if item_info is not None:
                matched += 1
                item_geo, item_cat = item_info
            else:
                unmatched += 1
                item_geo, item_cat = "", ""

            writer.writerow([
                row["user_id"],
                row["item_id"],
                row["behavior_type"],
                row["user_geohash"],
                row["item_category"],      # 行为表的 category
                row["time"],
                item_geo,                  # 商品表的 geohash
                item_cat,                  # 商品表的 category
            ])

    print(f"[JOIN] 匹配成功: {matched} 条, 未匹配: {unmatched} 条")


def main():
    print("=" * 60)
    print("  sample_extract.py — 从全量数据随机抽取 1 万条样本")
    print("=" * 60)

    # 1. 验证原始文件存在
    if not USER_CSV.exists():
        print(f"[ERROR] 用户行为表不存在: {USER_CSV}")
        sys.exit(1)
    if not ITEM_CSV.exists():
        print(f"[ERROR] 商品信息表不存在: {ITEM_CSV}")
        sys.exit(1)

    # 2. 统计总行数
    print(f"\n[STEP 1] 统计用户行为表行数...")
    total_user_lines = count_lines(USER_CSV)
    total_user_rows = total_user_lines - 1  # 去掉 header
    print(f"  用户行为表: {total_user_rows:,} 行数据 (含header共 {total_user_lines:,} 行)")

    # 3. 随机抽取行号
    print(f"\n[STEP 2] 随机抽取 {SAMPLE_SIZE:,} 个行号 (seed=42)...")
    chosen_lines = pick_line_numbers(total_user_lines, SAMPLE_SIZE, header_line=0)
    print(f"  已抽取 {len(chosen_lines):,} 个不重复行号")

    # 4. 提取选中行
    print(f"\n[STEP 3] 扫描 CSV 提取选中行...")
    user_rows = extract_rows(USER_CSV, chosen_lines)
    print(f"  提取到 {len(user_rows):,} 条记录")

    # 5. 加载商品表
    print(f"\n[STEP 4] 加载商品信息表...")
    item_map = load_item_table(ITEM_CSV)
    print(f"  商品表: {len(item_map):,} 个唯一 item_id")

    # 6. JOIN 并写出
    print(f"\n[STEP 5] 关联两表并输出 → {OUTPUT_CSV}")
    join_and_write(user_rows, item_map, OUTPUT_CSV)

    # 7. 最终统计
    print(f"\n{'=' * 60}")
    print(f"  完成！样本已输出到: {OUTPUT_CSV}")
    print(f"  输出列: user_id, item_id, behavior_type, user_geohash,")
    print(f"          user_item_category, time, item_geohash, item_item_category")
    print(f"  样本行数: {len(user_rows):,}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
