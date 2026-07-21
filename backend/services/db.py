"""MySQL 连接 + 常用查询（RFM 结果表 / 推荐结果表）。

这些结果由 B 的模型脚本产出、A 的 ADS 层写入 MySQL，C 只负责读。
"""
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE


def get_connection():
    import pymysql
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
        password=MYSQL_PASSWORD, database=MYSQL_DATABASE,
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_rfm():
    """读 RFM 8 类用户占比（供 /api/rfm/dist）。

    对齐 B 的 rfm_model.py 产出列：rfm_result 表含 rfm_label 列，
    每行一个用户，需要按标签聚合 COUNT。
    """
    # TODO(Day2): 接 A 的 ADS 层 rfm 结果表
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rfm_label AS label, COUNT(*) AS cnt "
                "FROM rfm_result GROUP BY rfm_label"
            )
            return cur.fetchall()


def get_recommend(user_id: int, limit: int = 10):
    """读某用户的推荐列表（供 /api/recommend）。

    对齐 B 的 recommender.py 产出（按 ai_design.md 含 reason 列）。
    若 B 的 recommend_result 表尚未包含 reason 列，自动降级只查 item_id/score。
    """
    # TODO(Day2): 接 B 的 recommender 产出表
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT item_id, score, reason FROM recommend_result "
                    "WHERE user_id=%s ORDER BY score DESC LIMIT %s",
                    (user_id, limit),
                )
            except Exception:
                # reason 列尚未建好时降级
                cur.execute(
                    "SELECT item_id, score FROM recommend_result "
                    "WHERE user_id=%s ORDER BY score DESC LIMIT %s",
                    (user_id, limit),
                )
            return cur.fetchall()


def get_report_latest():
    """读最新一期晨报（供 /api/report/latest）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT report_date, content, anomalies "
                "FROM morning_report ORDER BY report_date DESC LIMIT 1"
            )
            return cur.fetchone()


def get_report_history(days: int = 7):
    """读最近 N 天晨报列表（供 /api/report/history）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT report_date, content, anomalies "
                "FROM morning_report "
                "WHERE report_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
                "ORDER BY report_date DESC",
                (int(days),),
            )
            return cur.fetchall()
