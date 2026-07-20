"""
RFM 用户价值分群模型

基于用户行为数据计算 RFM 三维分值，通过三分位数分箱将用户划分为 8 类价值层级。

RFM 定义（适配本数据集）：
    R (Recency)  — 用户最近一次行为距数据截止日的天数（越小越好）
    F (Frequency) — 用户在统计周期内的购买次数（越多越好）
    M (Breadth)   — 用户购买涉及的去重商品数，替代传统金额维度（越多越好）

输入：data/tianchi_mobile_recommend_train_user.csv（约 1225 万行）
输出：rfm_result.csv（user_id, R, F, M, R_score, F_score, M_score, rfm_label）

使用方式：
    python analysis/rfm_model.py

或作为模块调用：
    from analysis.rfm_model import run_rfm
    df = run_rfm()  # 返回完整 RFM DataFrame
"""

import os
import sys
import time
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# 数据路径（相对于项目根目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_user.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "rfm_result.csv"

# 行为编码映射
BEHAVIOR_MAP = {1: "浏览", 2: "收藏", 3: "加购", 4: "购买"}

# 分块读取大小（行数）
CHUNK_SIZE = 500_000


# ============================================================
# 核心逻辑
# ============================================================

def _load_and_aggregate(data_path: str) -> pd.DataFrame:
    """
    分块读取 CSV，按用户聚合成中间统计表。

    每块内做 groupby 聚合，块间累加合并，避免一次性加载全部数据。
    """
    logger.info("Loading data from: %s", data_path)

    # 聚合中间结果：每个 user_id 的统计值
    agg = {}  # user_id -> {"last_time": max, "buy_cnt": sum, "buy_items": set}

    total_rows = 0
    chunk_idx = 0

    for chunk in pd.read_csv(
        data_path,
        chunksize=CHUNK_SIZE,
        dtype={
            "user_id": np.int64,
            "item_id": np.int64,
            "behavior_type": np.int8,
            "user_geohash": str,
            "item_category": np.int64,
            "time": str,
        },
    ):
        chunk_idx += 1
        total_rows += len(chunk)

        # 时间解析：2014-12-06 02 → datetime
        chunk["datetime"] = pd.to_datetime(chunk["time"], format="%Y-%m-%d %H")
        chunk["is_buy"] = (chunk["behavior_type"] == 4).astype(np.int16)

        # 按 user_id 分组聚合
        grouped = chunk.groupby("user_id")

        # 每个用户的最近行为时间
        for uid, grp in grouped:
            last_time = grp["datetime"].max()
            buy_cnt = grp["is_buy"].sum()
            buy_items = set(grp.loc[grp["behavior_type"] == 4, "item_id"].unique())

            if uid not in agg:
                agg[uid] = {
                    "last_time": last_time,
                    "buy_cnt": buy_cnt,
                    "buy_items": buy_items,
                }
            else:
                if last_time > agg[uid]["last_time"]:
                    agg[uid]["last_time"] = last_time
                agg[uid]["buy_cnt"] += buy_cnt
                agg[uid]["buy_items"] |= buy_items

        if chunk_idx % 5 == 0:
            logger.info("  Processed %d chunks, %d rows, %d users so far",
                        chunk_idx, total_rows, len(agg))

    logger.info("Aggregation done: %d rows, %d users", total_rows, len(agg))

    # 转换为 DataFrame
    rows = []
    for uid, stats in agg.items():
        rows.append({
            "user_id": uid,
            "last_time": stats["last_time"],
            "buy_cnt": stats["buy_cnt"],
            "buy_items_cnt": len(stats["buy_items"]),
        })

    return pd.DataFrame(rows)


def _compute_rfm(df: pd.DataFrame, ref_date: pd.Timestamp) -> pd.DataFrame:
    """基于聚合后的用户统计表计算 RFM 值。"""
    logger.info("Computing RFM scores (reference date: %s)", ref_date.strftime("%Y-%m-%d"))

    # R: 距截止日的天数（最近一次任意行为）
    df["R"] = (ref_date - df["last_time"]).dt.days

    # F: 购买次数
    df["F"] = df["buy_cnt"].astype(int)

    # M: 购买涉及的去重商品数（广度）
    df["M"] = df["buy_items_cnt"].astype(int)

    logger.info("RFM ranges: R=[%d, %d], F=[%d, %d], M=[%d, %d]",
                df["R"].min(), df["R"].max(),
                df["F"].min(), df["F"].max(),
                df["M"].min(), df["M"].max())

    return df


def _score_by_tertile(df: pd.DataFrame) -> pd.DataFrame:
    """
    三分位数分箱打分。

    R: 值越小越好 → 分值越高（3=最近活跃, 1=久未活跃）
    F: 值越大越好 → 分值越高（3=高频购买, 1=低频购买）
    M: 值越大越好 → 分值越高（3=购买广泛, 1=购买单一）

    使用 pd.qcut 的 category codes（0-based），手动映射到 1-3 分值。
    """
    logger.info("Scoring by tertile...")

    buyers = df[df["F"] > 0]

    def _safe_tertile(series: pd.Series, ascending: bool) -> pd.Series:
        """
        对 series 做三分位分箱，返回 1/2/3 分值。
        处理重复分位点导致的 bin 数量不足问题。
        """
        unique_vals = series.nunique()
        if unique_vals < 2:
            return pd.Series(1, index=series.index)

        n_bins = min(3, unique_vals)
        try:
            codes = pd.qcut(series, q=n_bins, labels=False, duplicates="drop")
        except ValueError:
            return pd.Series(1, index=series.index)

        # codes 是 0-based，映射到 1~n_bins（升序时 1=最小, n_bins=最大）
        score = codes + 1
        if not ascending:
            # 降序：值越小分值越高 → 翻转
            score = n_bins - codes
        return score.astype(int)

    # R: 值越小越好 → 升序分箱，再翻转（R 小 = 高分）
    df["R_score"] = _safe_tertile(df["R"], ascending=False)

    # F: 值越大越好（升序分箱，F 大 = 高分）
    df["F_score"] = 0
    if len(buyers) >= 2:
        df.loc[buyers.index, "F_score"] = _safe_tertile(buyers["F"], ascending=True)

    # M: 值越大越好（升序分箱，M 大 = 高分）
    df["M_score"] = 0
    if len(buyers) >= 2:
        df.loc[buyers.index, "M_score"] = _safe_tertile(buyers["M"], ascending=True)

    logger.info("Score distribution:\nR_score:\n%s\nF_score:\n%s\nM_score:\n%s",
                df["R_score"].value_counts().sort_index().to_string(),
                df["F_score"].value_counts().sort_index().to_string(),
                df["M_score"].value_counts().sort_index().to_string())

    return df


def _assign_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    基于 R/F/M 分值组合分配用户层级标签。

    8 类分层（R 高=活跃, R 低=流失; F 高=高频, F 低=低频; M 高=广泛, M 低=单一）：
    """
    logger.info("Assigning RFM labels...")

    def label_row(r, f, m):
        """根据三维分值返回中文标签"""
        if r >= 3 and f >= 3 and m >= 3:
            return "重要价值用户"
        elif r >= 3 and f >= 3 and m < 3:
            return "重要发展用户"
        elif r >= 3 and f < 3 and m >= 3:
            return "重要保持用户"
        elif r >= 3 and f < 3 and m < 3:
            return "新锐潜力用户"
        elif r < 3 and f >= 3 and m >= 3:
            return "重要挽留用户"
        elif r < 3 and f >= 3 and m < 3:
            return "一般价值用户"
        elif r < 3 and f < 3 and m >= 3:
            return "一般发展用户"
        else:
            return "低价值用户"

    df["rfm_label"] = df.apply(
        lambda row: label_row(row["R_score"], row["F_score"], row["M_score"]),
        axis=1,
    )

    # 无购买行为用户直接归为"浏览型用户"
    df.loc[df["F"] == 0, "rfm_label"] = "浏览型用户"

    return df


# ============================================================
# 主入口
# ============================================================

def run_rfm(data_path: str = None, output_path: str = None) -> pd.DataFrame:
    """
    执行完整 RFM 分群流程。

    Args:
        data_path:  原始 CSV 路径（默认读取 data/tianchi_mobile_recommend_train_user.csv）
        output_path: 结果输出路径（默认写入 data/rfm_result.csv）

    Returns:
        包含 user_id / R / F / M / R_score / F_score / M_score / rfm_label 的 DataFrame
    """
    t0 = time.time()

    data_path = data_path or str(DATA_PATH)
    output_path = output_path or str(OUTPUT_PATH)

    # 1. 分块读取 + 聚合
    df = _load_and_aggregate(data_path)

    # 2. 确定参考日期
    ref_date = df["last_time"].max()
    logger.info("Reference date (max time in data): %s", ref_date)

    # 3. 计算 RFM
    df = _compute_rfm(df, ref_date)

    # 4. 分箱打分
    df = _score_by_tertile(df)

    # 5. 分层标签
    df = _assign_labels(df)

    # 6. 输出结果（只保留需要的列）
    result = df[["user_id", "R", "F", "M", "R_score", "F_score", "M_score", "rfm_label"]].copy()
    result.to_csv(output_path, index=False, encoding="utf-8-sig")

    elapsed = time.time() - t0
    logger.info("RFM result saved to: %s (%.1f seconds)", output_path, elapsed)

    # 打印分布
    logger.info("\n%s", "=" * 50)
    logger.info("RFM User Distribution:\n%s", result["rfm_label"].value_counts().to_string())
    logger.info("=" * 50)

    return result


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    run_rfm()
