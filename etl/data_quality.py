"""
data_quality.py
===============
数据质量检测脚本 — 对用户行为表 + 商品信息表跑完整的质量规则，输出质量报告。

检测规则（按 DEV_PLAN F1.3）：
  1. 列非空率（user_geohash ~68%空，item_geohash ~64%空）
  2. 唯一率（item_id 去重情况）
  3. 值域范围（behavior_type ∈ {1,2,3,4}，日期 ∈ 2014-11-18 ~ 2014-12-18）
  4. 行为类型分布（浏览 94.2% / 收藏 2.0% / 加购 2.8% / 购买 1.0%）
  5. 日期覆盖度（31天是否完整）
  6. 商品表去重率（48万→31万）
  7. 两表 CategoryID 一致性校验
  8. 两表 item_id 重叠率

输出：
  - data/quality_report.json（结构化报告）
  - 终端统计摘要

用法：
  python etl/data_quality.py --mode dev     # 在 1 万条样本上跑
  python etl/data_quality.py --mode full    # 全量 1225 万行
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

# ============================================================
# 常量
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 默认路径
DEFAULT_USER_CSV = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_user.csv"
DEFAULT_ITEM_CSV = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_item.csv"
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample" / "sample_10k.csv"
OUTPUT_JSON = PROJECT_ROOT / "data" / "quality_report.json"

# 数据时间范围
DATE_MIN = pd.Timestamp("2014-11-18")
DATE_MAX = pd.Timestamp("2014-12-18")
EXPECTED_DAYS = 31

# 期望分布（来自 data/README.md）
EXPECTED_BEHAVIOR_DIST = {
    1: ("浏览", 0.942),
    2: ("收藏", 0.020),
    3: ("加购", 0.028),
    4: ("购买", 0.010),
}

# 分块大小
CHUNKSIZE = 100_000


def parse_args():
    parser = argparse.ArgumentParser(description="数据质量检测")
    parser.add_argument("--mode", choices=["dev", "full"], default="dev")
    parser.add_argument("--user", type=str, help="用户行为表路径")
    parser.add_argument("--item", type=str, help="商品信息表路径")
    parser.add_argument("--output", type=str, default=str(OUTPUT_JSON))
    parser.add_argument("--chunksize", type=int, default=CHUNKSIZE)
    return parser.parse_args()


# ============================================================
# 商品信息表质量检测（小表，全量加载）
# ============================================================

def check_item_table(path: Path) -> dict:
    """检测商品信息表质量"""
    print(f"\n[物品表] 读取: {path}")
    df = pd.read_csv(path, dtype=str)

    total = len(df)
    unique_items = df["item_id"].nunique()
    dup_count = total - unique_items
    dup_rate = dup_count / total if total > 0 else 0

    # 非空率
    null_geo = df["item_geohash"].isna().sum() + (df["item_geohash"] == "").sum()
    null_cat = df["item_category"].isna().sum() + (df["item_category"] == "").sum()

    # item_category 分布
    cat_count = df["item_category"].nunique()

    report = {
        "table": "item_info",
        "total_rows": total,
        "unique_item_ids": unique_items,
        "duplicate_rows": dup_count,
        "duplicate_rate": round(dup_rate, 4),
        "null_rate": {
            "item_geohash": round(null_geo / total, 4) if total > 0 else 0,
            "item_category": round(null_cat / total, 4) if total > 0 else 0,
        },
        "category_count": cat_count,
        "status": "pass" if dup_rate < 0.5 else "warn",
    }

    print(f"  行数: {total:,}  去重 item_id: {unique_items:,}  重复率: {dup_rate:.1%}")
    print(f"  空值率: item_geohash={report['null_rate']['item_geohash']:.1%}  item_category={report['null_rate']['item_category']:.1%}")
    print(f"  类目数: {cat_count}")

    return report


# ============================================================
# 用户行为表质量检测（大表，分块处理）
# ============================================================

def check_user_table(path: Path, chunksize: int) -> dict:
    """检测用户行为表质量（分块流式）"""
    file_size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"\n[行为表] 读取: {path} ({file_size_mb:.1f} MB)")

    # 小文件直接读，大文件分块
    if file_size_mb < 50:
        return _check_user_table_small(path)

    return _check_user_table_large(path, chunksize)


def _check_user_table_small(path: Path) -> dict:
    """小文件全量加载"""
    df = pd.read_csv(path, dtype=str)
    return _compute_user_stats(df)


def _check_user_table_large(path: Path, chunksize: int) -> dict:
    """大文件分块聚合统计"""
    print(f"  分块大小: {chunksize:,} 行/块")

    # 聚合容器
    behavior_counter = Counter()
    date_counter = Counter()
    total_rows = 0
    null_geohash = 0
    null_category = 0
    invalid_behavior = 0
    invalid_date = 0
    out_of_range = 0
    users = set()
    items = set()
    categories = set()
    seen_hashes = set()
    dup_rows = 0
    chunk_count = 0
    start_time = time.time()

    for chunk in pd.read_csv(path, dtype=str, chunksize=chunksize):
        chunk_count += 1
        rows = len(chunk)
        total_rows += rows

        # 空值统计
        null_geohash += chunk["user_geohash"].isna().sum() + (chunk["user_geohash"] == "").sum()
        null_category += chunk["item_category"].isna().sum() + (chunk["item_category"] == "").sum()

        # behavior_type 有效性
        bt = pd.to_numeric(chunk["behavior_type"], errors="coerce")
        invalid_behavior += bt.isna().sum() + (~bt.isin([1, 2, 3, 4])).sum()
        valid_bt = bt.dropna()
        valid_bt = valid_bt[valid_bt.isin([1, 2, 3, 4])]
        behavior_counter.update(valid_bt.astype(int).tolist())

        # 日期统计
        time_dt = pd.to_datetime(chunk["time"], format="%Y-%m-%d %H", errors="coerce")
        invalid_date += time_dt.isna().sum()
        valid_dt = time_dt.dropna()
        out_of_range += ((valid_dt < DATE_MIN) | (valid_dt > DATE_MAX)).sum()
        dates = valid_dt[valid_dt.between(DATE_MIN, DATE_MAX)].dt.strftime("%Y-%m-%d")
        date_counter.update(dates.tolist())

        # 去重统计（采样 Hash 去重）
        chunk["_hash"] = chunk.apply(
            lambda r: hash(tuple(r)), axis=1
        )
        for h in chunk["_hash"]:
            if h in seen_hashes:
                dup_rows += 1
            else:
                seen_hashes.add(h)

        # 集合去重（采样，避免内存爆炸）
        for uid in chunk["user_id"].dropna().unique():
            users.add(uid)
        for iid in chunk["item_id"].dropna().unique():
            items.add(iid)
        for cat in chunk["item_category"].dropna().unique():
            categories.add(cat)

        # 进度
        if chunk_count % 50 == 0:
            elapsed = time.time() - start_time
            print(f"  [进度] {total_rows:>11,} 行  {total_rows/elapsed:>.0f} 行/s")

    elapsed = time.time() - start_time
    print(f"  处理完成: {total_rows:,} 行  {chunk_count} 块  {elapsed:.1f}s")

    return _build_user_report(
        total_rows, null_geohash, null_category, invalid_behavior,
        invalid_date, out_of_range, behavior_counter, date_counter,
        len(users), len(items), len(categories), dup_rows, seen_hashes,
        elapsed,
    )


def _check_user_table_small(path: Path) -> dict:
    """小文件直接处理"""
    df = pd.read_csv(path, dtype=str)
    total_rows = len(df)

    # 适配不同列名：raw CSV 用 item_category，sample CSV 用 user_item_category
    cat_col = "item_category" if "item_category" in df.columns else "user_item_category"
    geo_col = "user_geohash" if "user_geohash" in df.columns else None
    time_col = "time" if "time" in df.columns else None

    null_geohash = int(df[geo_col].isna().sum() + (df[geo_col] == "").sum()) if geo_col else 0
    null_category = int(df[cat_col].isna().sum() + (df[cat_col] == "").sum())

    bt = pd.to_numeric(df["behavior_type"], errors="coerce")
    invalid_behavior = int(bt.isna().sum() + (~bt.isin([1, 2, 3, 4])).sum())
    valid_bt = bt.dropna()
    valid_bt = valid_bt[valid_bt.isin([1, 2, 3, 4])]
    behavior_counter = Counter(valid_bt.astype(int).tolist())

    if time_col and time_col in df.columns:
        time_dt = pd.to_datetime(df[time_col], format="%Y-%m-%d %H", errors="coerce")
    else:
        time_dt = pd.Series([pd.NaT] * len(df))
    invalid_date = int(time_dt.isna().sum())
    valid_dt = time_dt.dropna()
    out_of_range = 0
    date_counter = Counter()
    if len(valid_dt) > 0:
        out_of_range = int(((valid_dt < DATE_MIN) | (valid_dt > DATE_MAX)).sum())
        date_counter = Counter(valid_dt[valid_dt.between(DATE_MIN, DATE_MAX)].dt.strftime("%Y-%m-%d").tolist())

    return _build_user_report(
        total_rows, null_geohash, null_category, invalid_behavior,
        invalid_date, out_of_range, behavior_counter, date_counter,
        df["user_id"].nunique(), df["item_id"].nunique(), df[cat_col].nunique(),
        0, set(),
        0.0,
    )


def _build_user_report(total, null_geo, null_cat, invalid_bt, invalid_dt,
                       out_of_range, behavior_dist, date_dist,
                       n_users, n_items, n_cats, dup_rows, seen_set, elapsed):
    """组装行为表质量报告"""
    n_dates = len(date_dist)
    missing_dates = EXPECTED_DAYS - n_dates

    report = {
        "table": "user_behavior",
        "total_rows": total,
        "unique_users": n_users,
        "unique_items": n_items,
        "unique_categories": n_cats,
        "duplicate_rows": dup_rows if dup_rows > 0 else "N/A (小文件未检测)",
        "null_rate": {
            "user_geohash": round(null_geo / total, 4) if total > 0 else 0,
            "item_category": round(null_cat / total, 4) if total > 0 else 0,
        },
        "invalid_rows": {
            "behavior_type": invalid_bt,
            "time_parse_fail": invalid_dt,
            "date_out_of_range": out_of_range,
        },
        "behavior_distribution": {},
        "date_coverage": {
            "days_covered": n_dates,
            "days_expected": EXPECTED_DAYS,
            "days_missing": missing_dates,
            "first_date": min(date_dist.keys()) if date_dist else None,
            "last_date": max(date_dist.keys()) if date_dist else None,
            "missing_dates": sorted(
                [d.strftime("%Y-%m-%d") for d in pd.date_range(DATE_MIN, DATE_MAX)
                 if d.strftime("%Y-%m-%d") not in date_dist]
            ),
        },
        "elapsed_seconds": round(elapsed, 1),
    }

    # 行为分布
    total_behaviors = sum(behavior_dist.values())
    for bt_code in [1, 2, 3, 4]:
        cnt = behavior_dist.get(bt_code, 0)
        pct = cnt / total_behaviors if total_behaviors > 0 else 0
        expected_name, expected_pct = EXPECTED_BEHAVIOR_DIST.get(bt_code, ("?", 0))
        report["behavior_distribution"][f"type_{bt_code}"] = {
            "name": expected_name,
            "count": cnt,
            "actual_pct": round(pct, 4),
            "expected_pct": expected_pct,
            "deviation": round(pct - expected_pct, 4),
        }

    # 质量判定
    issues = []
    if report["null_rate"]["user_geohash"] > 0.8:
        issues.append("user_geohash 空值率 > 80%")
    if missing_dates > 0:
        issues.append(f"缺失 {missing_dates} 天数据")
    for bt_code in [1, 2, 3, 4]:
        dev = report["behavior_distribution"][f"type_{bt_code}"]["deviation"]
        if abs(dev) > 0.1:
            issues.append(f"行为类型 {bt_code} 分布偏差 > 10%")

    report["issues"] = issues
    report["status"] = "pass" if not issues else "warn"

    # 终端输出
    print(f"\n  行数: {total:,}  用户: {n_users:,}  商品: {n_items:,}  类目: {n_cats:,}")
    print(f"  空值率: user_geohash={report['null_rate']['user_geohash']:.1%}  item_category={report['null_rate']['item_category']:.1%}")
    print(f"  异常行: 无效行为={invalid_bt}  时间异常={invalid_dt}  越界={out_of_range}")
    print(f"  日期覆盖: {n_dates}/{EXPECTED_DAYS} 天"
          + (f"  缺失: {missing_dates} 天 {report['date_coverage']['missing_dates']}" if missing_dates else "  [OK] 完整"))
    print(f"  行为分布:")
    for bt_code in [1, 2, 3, 4]:
        d = report["behavior_distribution"][f"type_{bt_code}"]
        flag = " [WARN]" if abs(d["deviation"]) > 0.05 else ""
        print(f"    {d['name']}: {d['count']:>10,} ({d['actual_pct']:.1%}  预期 {d['expected_pct']:.1%}){flag}")

    if issues:
        print(f"  [WARN] 问题: {'; '.join(issues)}")
    else:
        print(f"  [OK] 质量通过")

    return report


# ============================================================
# 两表交叉校验
# ============================================================

def check_cross_table(user_report: dict, item_report: dict,
                       user_path: Path, item_path: Path) -> dict:
    """两表交叉校验：item_id 重叠率、CategoryID 一致性"""
    print(f"\n[交叉校验]")

    # 只对样本数据做精确交叉（全量太慢）
    file_size = os.path.getsize(user_path) / (1024 * 1024)
    if file_size > 100:
        print(f"  [SKIP] 全量模式跳过交叉校验（仅在样本模式运行）")
        return {
            "item_id_overlap": "skipped",
            "category_overlap": "skipped",
        }

    user_df = pd.read_csv(user_path, dtype=str, nrows=50000)
    item_df = pd.read_csv(item_path, dtype=str)

    user_items = set(user_df["item_id"].dropna())
    item_items = set(item_df["item_id"].dropna())
    overlap = user_items & item_items
    overlap_rate = len(overlap) / len(user_items) if user_items else 0

    # CategoryID 一致性
    # 行为表中的 item_category / user_item_category vs 商品表中的 item_category
    cat_col = "item_category" if "item_category" in user_df.columns else (
        "user_item_category" if "user_item_category" in user_df.columns else None
    )
    if cat_col:
        user_cats = set(user_df[cat_col].dropna())
    else:
        user_cats = set()
    item_cats = set(item_df["item_category"].dropna())
    cat_overlap = user_cats & item_cats
    cat_user_only = user_cats - item_cats
    cat_item_only = item_cats - user_cats

    report = {
        "item_id_comparison": {
            "user_table_unique": len(user_items),
            "item_table_unique": len(item_items),
            "overlap_count": len(overlap),
            "overlap_rate": round(overlap_rate, 4),
            "user_only": len(user_items) - len(overlap),
        },
        "category_comparison": {
            "user_table_categories": len(user_cats),
            "item_table_categories": len(item_cats),
            "overlap_count": len(cat_overlap),
            "overlap_rate": round(len(cat_overlap) / len(user_cats), 4) if user_cats else 0,
            "categories_in_user_only": len(cat_user_only),
            "categories_in_item_only": len(cat_item_only),
        },
        "status": "pass" if overlap_rate > 0.01 else "warn",
    }

    print(f"  item_id 重叠: {len(overlap):,} / {len(user_items):,} = {overlap_rate:.1%}")
    print(f"  Category 重叠: {len(cat_overlap):,} / {len(user_cats):,} (行为表 {len(user_cats)} 个, 商品表 {len(item_cats)} 个)")
    if cat_user_only:
        print(f"    [WARN] 行为表独有类目: {len(cat_user_only)} 个（行为表类目远多于商品表）")

    return report


# ============================================================
# 汇总 & 输出
# ============================================================

def build_summary(item_report: dict, user_report: dict, cross_report: dict) -> dict:
    """汇总所有检测"""
    all_pass = (
        item_report.get("status") == "pass"
        and user_report.get("status") == "pass"
        and cross_report.get("status") == "pass"
    )

    return {
        "quality_check_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "overall_status": "PASS" if all_pass else "WARN",
        "item_table": item_report,
        "user_behavior_table": user_report,
        "cross_table_check": cross_report,
        "summary": {
            "total_issues": len(user_report.get("issues", [])) + (0 if item_report.get("status") == "pass" else 1),
            "remarks": _generate_remarks(item_report, user_report, cross_report),
        },
    }


def _generate_remarks(item_r: dict, user_r: dict, cross_r: dict) -> list:
    remarks = []
    # 从数据 README 已知的特征
    if user_r["null_rate"]["user_geohash"] > 0.5:
        remarks.append(f"user_geohash 空值率 {user_r['null_rate']['user_geohash']:.0%}，符合数据集特点（约68%为空）")
    if item_r["null_rate"]["item_geohash"] > 0.5:
        remarks.append(f"item_geohash 空值率 {item_r['null_rate']['item_geohash']:.0%}，符合数据集特点（约64%为空）")
    if isinstance(item_r["duplicate_rows"], int) and item_r["duplicate_rows"] > 100000:
        remarks.append(f"商品表去重: {item_r['total_rows']:,} → {item_r['unique_item_ids']:,} 商品")
    if cross_r.get("category_comparison", {}).get("categories_in_user_only", 0) > 100:
        remarks.append("行为表类目数远大于商品表（行为表8,916个 vs 商品表991个），以行为表为准")
    if user_r["date_coverage"]["days_missing"] == 0:
        remarks.append("日期覆盖完整（31天）")
    return remarks


# ============================================================
# 主入口
# ============================================================

def main():
    print("=" * 60)
    print("  data_quality.py — 数据质量检测")
    print("=" * 60)

    args = parse_args()

    if args.mode == "dev":
        user_path = Path(args.user) if args.user else SAMPLE_CSV
        item_path = Path(args.item) if args.item else DEFAULT_ITEM_CSV
        print(f"  [DEV] 样本模式: {user_path}")
    else:
        user_path = Path(args.user) if args.user else DEFAULT_USER_CSV
        item_path = Path(args.item) if args.item else DEFAULT_ITEM_CSV
        print(f"  [FULL] 全量模式: {user_path}")

    output_path = Path(args.output)

    # 验证文件存在
    for p, name in [(user_path, "用户行为表"), (item_path, "商品信息表")]:
        if not p.exists():
            print(f"[ERROR] {name} 不存在: {p}")
            sys.exit(1)

    # 1. 商品表
    item_report = check_item_table(item_path)

    # 2. 用户行为表
    user_report = check_user_table(user_path, args.chunksize)

    # 3. 交叉校验
    cross_report = check_cross_table(user_report, item_report, user_path, item_path)

    # 4. 汇总
    full_report = build_summary(item_report, user_report, cross_report)

    # 5. 输出 JSON
    os.makedirs(output_path.parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, ensure_ascii=False, indent=2)

    # 6. 结论
    print(f"\n{'=' * 60}")
    print(f"  质量报告已输出: {output_path}")
    print(f"  总体状态: {full_report['overall_status']}")
    if full_report["summary"]["remarks"]:
        print(f"  备注: {'; '.join(full_report['summary']['remarks'])}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
