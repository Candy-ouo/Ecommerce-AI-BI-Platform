"""
Item-CF 协同过滤推荐

基于用户购买行为构建 User-Item 矩阵，计算商品间余弦相似度，为每个用户推荐
其未购买过的相似商品。

核心流程：
    1. 从 CSV 提取购买记录（behavior_type=4）
    2. 过滤冷门商品（购买数 < MIN_ITEM_PURCHASES），构建稀疏矩阵
    3. 计算 Item-Item 余弦相似度
    4. 对每个已购商品取 TopK 相似商品，汇总排序 → TopN 推荐

输入：data/tianchi_mobile_recommend_train_user.csv
输出：data/recommend_result.csv（user_id, item_id, score）

使用方式：
    python analysis/recommender.py
"""

import os
import sys
import time
import logging
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, lil_matrix, coo_matrix
from sklearn.metrics.pairwise import cosine_similarity

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_user.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "recommend_result.csv"

CHUNK_SIZE = 500_000

# 超参数
MIN_ITEM_PURCHASES = 3      # 商品至少被购买 N 次才纳入推荐池
TOP_K_SIMILAR = 50          # 每个商品取 TopK 相似商品
TOP_N_RECOMMEND = 10        # 每个用户推荐 TopN 商品


# ============================================================
# 数据加载
# ============================================================

def _load_purchase_data(data_path: str) -> tuple:
    """
    分块读取 CSV，只提取购买行为。

    Returns:
        (user_item_pairs, item_purchase_counts)
        user_item_pairs: [(user_id, item_id), ...]
        item_purchase_counts: {item_id: count}
    """
    logger.info("Loading purchase data from: %s", data_path)

    user_items = []  # list of (user_id, item_id)
    item_counts = defaultdict(int)
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

        buys = chunk[chunk["behavior_type"] == 4]
        for _, row in buys.iterrows():
            uid, iid = row["user_id"], row["item_id"]
            user_items.append((uid, iid))
            item_counts[iid] += 1

        if chunk_idx % 5 == 0:
            logger.info("  Processed %d chunks, %d rows, %d purchases so far",
                        chunk_idx, total_rows, len(user_items))

    logger.info("Done: %d total rows, %d purchases, %d unique items purchased",
                total_rows, len(user_items), len(item_counts))

    return user_items, item_counts


# ============================================================
# 矩阵构建与相似度计算
# ============================================================

def _build_similarity_matrix(user_items: list, item_counts: dict) -> tuple:
    """
    构建稀疏矩阵并计算 Item-Item 相似度。

    步骤：
        1. 过滤冷门商品 → 建立 user_id / item_id 到矩阵行列的映射
        2. 构建 user-item 稀疏矩阵（行=用户, 列=商品, 值=1）
        3. 转置为 item-user 矩阵 → 计算 item-item 余弦相似度

    Returns:
        (item_sim_matrix, user_idx_map, item_idx_map, popular_items)
    """
    # 过滤热门商品
    popular_items = {iid for iid, cnt in item_counts.items() if cnt >= MIN_ITEM_PURCHASES}
    logger.info("Items with >= %d purchases: %d / %d",
                MIN_ITEM_PURCHASES, len(popular_items), len(item_counts))

    if len(popular_items) == 0:
        raise RuntimeError("No items meet the minimum purchase threshold")

    # 只保留热门商品的购买记录
    filtered = [(uid, iid) for uid, iid in user_items if iid in popular_items]

    # 构建 user_id ↔ row, item_id ↔ col 映射
    user_ids = sorted(set(uid for uid, _ in filtered))
    item_ids = sorted(popular_items)

    user_to_row = {uid: i for i, uid in enumerate(user_ids)}
    item_to_col = {iid: j for j, iid in enumerate(item_ids)}

    n_users = len(user_ids)
    n_items = len(item_ids)
    logger.info("Matrix: %d users x %d items", n_users, n_items)

    # 构建 COO 稀疏矩阵
    rows = []
    cols = []
    for uid, iid in filtered:
        rows.append(user_to_row[uid])
        cols.append(item_to_col[iid])

    data = np.ones(len(rows), dtype=np.float32)
    user_item_matrix = coo_matrix(
        (data, (rows, cols)), shape=(n_users, n_items), dtype=np.float32
    ).tocsr()

    sparsity = 1 - (user_item_matrix.nnz / (n_users * n_items))
    logger.info("Sparsity: %.4f%%", sparsity * 100)

    # 转置为 item-user 矩阵，计算 item-item 余弦相似度
    item_user_matrix = user_item_matrix.T.tocsr()
    logger.info("Computing item-item cosine similarity (%d x %d)...", n_items, n_items)

    item_sim = cosine_similarity(item_user_matrix, dense_output=False)

    logger.info("Similarity matrix: %d non-zero entries", item_sim.nnz)

    return item_sim, user_ids, item_ids, user_to_row, item_to_col, n_items


# ============================================================
# 推荐生成
# ============================================================

def _generate_recommendations(
    item_sim,
    user_ids: list,
    item_ids: list,
    user_to_row: dict,
    item_to_col: dict,
    n_items: int,
    user_items: list,
    popular_items: set,
) -> pd.DataFrame:
    """
    为每个用户生成 TopN 推荐。

    对每个用户：
        1. 取该用户已购商品集合
        2. 对每个已购商品，取最为相似的 TopK 商品
        3. 汇总所有候选商品的相似度得分
        4. 排除已购商品，排序取 TopN
    """
    logger.info("Generating recommendations for %d users...", len(user_ids))

    # 构建用户已购商品集合（只含热门商品）
    user_bought = defaultdict(set)
    for uid, iid in user_items:
        if iid in popular_items:
            user_bought[uid].add(item_to_col[iid])

    # 为每个商品预取 TopK 相似商品（稀疏矩阵索引，加速计算）
    item_sim_csr = item_sim.tocsr()
    item_topk = {}  # col_idx → [(similar_col_idx, score), ...]

    for col_idx in range(n_items):
        row = item_sim_csr.getrow(col_idx)
        if row.nnz == 0:
            item_topk[col_idx] = []
            continue
        # 取相似度最高的 K+1 个（排除自己）
        scores = row.toarray().ravel()
        top_indices = np.argpartition(scores, -(TOP_K_SIMILAR + 1))[-(TOP_K_SIMILAR + 1):]
        top_indices = top_indices[scores[top_indices] > 0]
        # 排除自己
        top_indices = top_indices[top_indices != col_idx]
        top_pairs = [(int(i), float(scores[i])) for i in top_indices]
        top_pairs.sort(key=lambda x: x[1], reverse=True)
        item_topk[col_idx] = top_pairs[:TOP_K_SIMILAR]

    # 生成推荐
    results = []
    user_count = 0

    for uid in user_ids:
        row_idx = user_to_row[uid]
        bought_cols = user_bought.get(uid, set())

        if not bought_cols:
            continue

        # 汇总候选商品得分
        candidate_scores = defaultdict(float)
        for col_idx in bought_cols:
            for sim_col, sim_score in item_topk.get(col_idx, []):
                if sim_col not in bought_cols:
                    candidate_scores[sim_col] += sim_score

        if not candidate_scores:
            continue

        # 排序取 TopN
        sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
        for sim_col, score in sorted_candidates[:TOP_N_RECOMMEND]:
            results.append({
                "user_id": uid,
                "item_id": item_ids[sim_col],
                "score": round(score, 4),
            })

        user_count += 1
        if user_count % 1000 == 0:
            logger.info("  Generated for %d users...", user_count)

    df = pd.DataFrame(results)
    logger.info("Generated %d recommendations for %d users", len(df), user_count)
    return df


# ============================================================
# 主入口
# ============================================================

def run_recommender(data_path: str = None, output_path: str = None) -> pd.DataFrame:
    """
    执行完整 Item-CF 推荐流程。

    Returns:
        DataFrame with columns: user_id, item_id, score
    """
    t0 = time.time()

    data_path = data_path or str(DATA_PATH)
    output_path = output_path or str(OUTPUT_PATH)

    # 1. 加载购买数据
    user_items, item_counts = _load_purchase_data(data_path)

    # 2. 构建相似度矩阵
    item_sim, user_ids, item_ids, user_to_row, item_to_col, n_items = \
        _build_similarity_matrix(user_items, item_counts)

    # 3. 生成推荐
    # 过滤后的热门商品集合（与 _build_similarity_matrix 一致）
    filtered_items = {iid for iid, cnt in item_counts.items() if cnt >= MIN_ITEM_PURCHASES}
    result = _generate_recommendations(
        item_sim, user_ids, item_ids, user_to_row, item_to_col,
        n_items, user_items, filtered_items,
    )

    # 4. 保存
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    elapsed = time.time() - t0

    logger.info("=" * 50)
    logger.info("Recommendations saved to: %s", output_path)
    logger.info("  Users with recommendations: %d", result["user_id"].nunique())
    logger.info("  Total recommendations: %d", len(result))
    logger.info("  Avg score: %.4f", result["score"].mean())
    logger.info("  Time: %.1f seconds", elapsed)
    logger.info("=" * 50)

    return result


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    run_recommender()
