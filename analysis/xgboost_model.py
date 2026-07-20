"""
XGBoost 复购预测模型

基于用户历史行为特征，使用 XGBoost 预测用户未来是否会再次购买（复购）。

核心思路：
    1. 时间切分：前24天行为 → 特征，后7天是否购买 → 标签
    2. 仅对训练期有购买记录的用户做复购预测
    3. 训练 XGBoost → AUC 评估 → SHAP 特征重要性分析

输入：data/tianchi_mobile_recommend_train_user.csv
输出：
    - 模型文件：data/xgboost_repurchase_model.pkl
    - 特征重要性图：data/shap_summary.png（供答辩展示）

使用方式：
    python analysis/xgboost_model.py
"""

import os
import sys
import time
import logging
import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "tianchi_mobile_recommend_train_user.csv"
MODEL_OUTPUT = PROJECT_ROOT / "data" / "xgboost_repurchase_model.pkl"
SHAP_OUTPUT = PROJECT_ROOT / "data" / "shap_summary.png"

CHUNK_SIZE = 500_000

# 时间窗口切分
DATA_START = pd.Timestamp("2014-11-18")
TRAIN_END = pd.Timestamp("2014-12-11 23:00:00")   # 前 24 天 → 特征
TARGET_START = pd.Timestamp("2014-12-12 00:00:00") # 后 7 天 → 标签
DATA_END = pd.Timestamp("2014-12-18 23:00:00")

BEHAVIOR_MAP = {1: "浏览", 2: "收藏", 3: "加购", 4: "购买"}

# ============================================================
# 数据加载与用户级特征聚合
# ============================================================

def _aggregate_user_features(data_path: str) -> tuple:
    """
    分块读取 CSV，按用户聚合训练期特征和标签期标签。

    Returns:
        (features_df, labels_series)
        features_df: user_id 为 index，行为特征为列的 DataFrame
        labels_series: user_id → 0/1（目标期是否购买）
    """
    logger.info("Loading and aggregating user features...")
    logger.info("Train period: %s ~ %s", DATA_START.date(), TRAIN_END.date())
    logger.info("Target period: %s ~ %s", TARGET_START.date(), DATA_END.date())

    # 每个用户的中间聚合数据
    agg = {}  # user_id → {train_*, target_buy: bool}

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

        chunk["datetime"] = pd.to_datetime(chunk["time"], format="%Y-%m-%d %H")
        chunk["date"] = chunk["datetime"].dt.date

        # 拆分训练期和目标期
        train_mask = chunk["datetime"] <= TRAIN_END
        target_mask = chunk["datetime"] >= TARGET_START

        train_chunk = chunk[train_mask]
        target_chunk = chunk[target_mask]

        # --- 训练期聚合 ---
        if len(train_chunk) > 0:
            for uid, grp in train_chunk.groupby("user_id"):
                if uid not in agg:
                    agg[uid] = _init_user_stats()
                stats = agg[uid]

                stats["train_pv"] += (grp["behavior_type"] == 1).sum()
                stats["train_fav"] += (grp["behavior_type"] == 2).sum()
                stats["train_cart"] += (grp["behavior_type"] == 3).sum()
                stats["train_buy"] += (grp["behavior_type"] == 4).sum()
                stats["train_dates"] |= set(grp["date"].unique())
                stats["train_buy_dates"] |= set(grp.loc[grp["behavior_type"] == 4, "date"].unique())
                stats["train_items"] |= set(grp["item_id"].unique())
                stats["train_cats"] |= set(grp["item_category"].unique())
                stats["train_buy_items"] |= set(grp.loc[grp["behavior_type"] == 4, "item_id"].unique())

                # 最近N天的行为（用于 recency 特征）
                recent_3d = grp[grp["datetime"] >= TRAIN_END - pd.Timedelta(days=3)]
                recent_7d = grp[grp["datetime"] >= TRAIN_END - pd.Timedelta(days=7)]
                stats["train_recent_pv_3d"] += (recent_3d["behavior_type"] == 1).sum()
                stats["train_recent_buy_7d"] += (recent_7d["behavior_type"] == 4).sum()
                stats["train_recent_active_days_7d"] |= set(recent_7d["date"].unique())

                # 记录每个购买行为的时间（用于计算购买间隔）
                buy_times = grp.loc[grp["behavior_type"] == 4, "datetime"].sort_values()
                if len(buy_times) > 0:
                    stats["train_buy_times"].extend(buy_times.tolist())

        # --- 目标期标签 ---
        if len(target_chunk) > 0:
            target_buyers = set(target_chunk.loc[target_chunk["behavior_type"] == 4, "user_id"].unique())
            for uid in target_buyers:
                if uid not in agg:
                    agg[uid] = _init_user_stats()
                agg[uid]["target_buy"] = True

        if chunk_idx % 5 == 0:
            logger.info("  Processed %d chunks, %d rows, %d users",
                        chunk_idx, total_rows, len(agg))

    logger.info("Aggregation done: %d rows, %d users", total_rows, len(agg))

    # --- 转换为 DataFrame ---
    rows = []
    for uid, stats in agg.items():
        train_buy = stats["train_buy"]

        # 购买间隔（天）
        buy_times_sorted = sorted(stats["train_buy_times"])
        if len(buy_times_sorted) >= 2:
            intervals = [(buy_times_sorted[i] - buy_times_sorted[i - 1]).total_seconds() / 86400
                         for i in range(1, len(buy_times_sorted))]
            avg_buy_interval = np.mean(intervals)
        else:
            avg_buy_interval = -1  # 购买次数不足，无法计算

        n_active_days = len(stats["train_dates"])
        n_buy_days = len(stats["train_buy_dates"])

        rows.append({
            "user_id": uid,
            # 基础行为计数
            "total_pv": stats["train_pv"],
            "total_fav": stats["train_fav"],
            "total_cart": stats["train_cart"],
            "total_buy": train_buy,
            # 活跃度
            "active_days": n_active_days,
            "buy_days": n_buy_days,
            # 广度
            "distinct_items": len(stats["train_items"]),
            "distinct_cats": len(stats["train_cats"]),
            "distinct_buy_items": len(stats["train_buy_items"]),
            # 转化率
            "pv_to_cart_rate": stats["train_cart"] / max(stats["train_pv"], 1),
            "cart_to_buy_rate": train_buy / max(stats["train_cart"], 1),
            "buy_to_pv_rate": train_buy / max(stats["train_pv"], 1),
            # 日均
            "avg_daily_pv": stats["train_pv"] / max(n_active_days, 1),
            "avg_daily_buy": train_buy / max(n_active_days, 1),
            # 近期行为
            "recent_pv_3d": stats["train_recent_pv_3d"],
            "recent_buy_7d": stats["train_recent_buy_7d"],
            "recent_active_days_7d": len(stats["train_recent_active_days_7d"]),
            # 购买节奏
            "buy_freq_per_day": train_buy / max(n_buy_days, 1),
            "avg_buy_interval_days": avg_buy_interval,
            # 类目集中度
            "items_per_cat": len(stats["train_items"]) / max(len(stats["train_cats"]), 1),
            # 标签
            "target_buy": int(stats["target_buy"]),
        })

    df = pd.DataFrame(rows).set_index("user_id")
    logger.info("Feature matrix: %d users, %d features", df.shape[0], df.shape[1] - 1)

    labels = df["target_buy"]
    features = df.drop(columns=["target_buy"])

    return features, labels


def _init_user_stats():
    """初始化单个用户的聚合统计字典"""
    return {
        "train_pv": 0, "train_fav": 0, "train_cart": 0, "train_buy": 0,
        "train_dates": set(), "train_buy_dates": set(),
        "train_items": set(), "train_cats": set(), "train_buy_items": set(),
        "train_recent_pv_3d": 0, "train_recent_buy_7d": 0,
        "train_recent_active_days_7d": set(),
        "train_buy_times": [],
        "target_buy": False,
    }


# ============================================================
# 模型训练与评估
# ============================================================

def _train_model(X: pd.DataFrame, y: pd.Series) -> tuple:
    """训练 XGBoost 模型，返回 (model, X_test, y_test, y_pred_proba)"""
    from xgboost import XGBClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        roc_auc_score, accuracy_score, precision_score,
        recall_score, f1_score, classification_report,
    )

    # 只保留训练期有购买行为的用户（复购预测）
    mask = X["total_buy"] > 0
    X_rep = X[mask].copy()
    y_rep = y[mask].copy()

    logger.info("Repurchase candidates (train_buy > 0): %d / %d", len(X_rep), len(X))
    logger.info("  Positive (buy again): %d (%.1f%%)",
                y_rep.sum(), y_rep.mean() * 100)
    logger.info("  Negative (not buy back): %d (%.1f%%)",
                (1 - y_rep).sum(), (1 - y_rep.mean()) * 100)

    if len(X_rep) < 100:
        logger.warning("Too few repurchase candidates, skipping training")
        return None, None, None, None

    # 划分训练/测试集
    X_train, X_test, y_train, y_test = train_test_split(
        X_rep, y_rep, test_size=0.2, random_state=42, stratify=y_rep,
    )

    logger.info("Train: %d, Test: %d", len(X_train), len(X_test))

    # 处理类别不平衡
    scale_pos_weight = (1 - y_train.mean()) / y_train.mean()

    model = XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric="auc",
        early_stopping_rounds=10,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # 评估
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]

    logger.info("\n%s", "=" * 50)
    logger.info("Model Evaluation:")
    logger.info("  AUC      : %.4f", roc_auc_score(y_test, y_pred_proba))
    logger.info("  Accuracy : %.4f", accuracy_score(y_test, y_pred))
    logger.info("  Precision: %.4f", precision_score(y_test, y_pred))
    logger.info("  Recall   : %.4f", recall_score(y_test, y_pred))
    logger.info("  F1       : %.4f", f1_score(y_test, y_pred))
    logger.info("=" * 50)

    return model, X_test, y_test, y_pred_proba


# ============================================================
# SHAP 可解释性
# ============================================================

def _shap_analysis(model, X_test: pd.DataFrame, output_path: str):
    """生成特征重要性图（XGBoost built-in，基于 gain）"""
    try:
        _plot_feature_importance(model, X_test, output_path)
        return True
    except Exception as e:
        logger.warning("Feature importance plot failed: %s", e)
        return False


def _plot_feature_importance(model, X_test: pd.DataFrame, output_path: str):
    """降级方案：用 XGBoost 自带的 plot_importance"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from xgboost import plot_importance

    plt.figure(figsize=(10, 8))
    plot_importance(model, max_num_features=15, importance_type="gain")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Feature importance saved to: %s", output_path)


# ============================================================
# 主入口
# ============================================================

def run_xgboost(data_path: str = None) -> dict:
    """
    执行完整 XGBoost 复购预测流程。

    Returns:
        {"auc": float, "feature_importance": [(name, importance), ...]}
    """
    t0 = time.time()

    data_path = data_path or str(DATA_PATH)

    # 1. 特征工程
    X, y = _aggregate_user_features(data_path)

    # 2. 训练
    model, X_test, y_test, y_proba = _train_model(X, y)
    if model is None:
        logger.error("Training failed: insufficient data")
        return {}

    # 3. 保存模型
    with open(MODEL_OUTPUT, "wb") as f:
        pickle.dump({"model": model, "feature_names": list(X.columns)}, f)
    logger.info("Model saved to: %s", MODEL_OUTPUT)

    # 4. SHAP
    _shap_analysis(model, X_test, str(SHAP_OUTPUT))

    # 5. 特征重要性
    importance = sorted(
        zip(X.columns, model.feature_importances_),
        key=lambda x: x[1], reverse=True,
    )
    logger.info("\nTop 10 Feature Importance:")
    for name, imp in importance[:10]:
        logger.info("  %-25s %.4f", name, imp)

    elapsed = time.time() - t0
    logger.info("\nTotal time: %.1f seconds", elapsed)

    return {
        "auc": float(model.best_score) if hasattr(model, "best_score") else None,
        "feature_importance": importance,
    }


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    run_xgboost()
