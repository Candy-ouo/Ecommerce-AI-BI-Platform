"""本地环境连通性测试：MySQL + Hive。

运行：python tests/test_connectivity.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_mysql():
    """MySQL 连通 + 表结构验证 + 测试数据写入"""
    import pymysql
    conn = pymysql.connect(host="localhost", port=3306, user="root", password="123456")
    cur = conn.cursor()

    # 建库
    cur.execute("CREATE DATABASE IF NOT EXISTS ecommerce_bi CHARACTER SET utf8mb4")
    conn.commit()

    # 晨报表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ecommerce_bi.morning_report (
            id INT AUTO_INCREMENT PRIMARY KEY,
            report_date DATE NOT NULL,
            content TEXT,
            anomalies JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # 推荐表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ecommerce_bi.recommends (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            item_id BIGINT NOT NULL,
            score FLOAT,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # 测试数据
    cur.execute("DELETE FROM ecommerce_bi.recommends")
    cur.execute("DELETE FROM ecommerce_bi.morning_report")

    cur.execute("""
        INSERT INTO ecommerce_bi.morning_report (report_date, content, anomalies)
        VALUES ('2014-12-18',
            '今日 DAU 12,345（环比 +3.2%），总订单 8,900 单。全站转化率 4.2%。数码品类表现突出，浏览量环比增长 15%。',
            '["数码品类销量增长15%", "服饰品类收藏率下降5%"]')
    """)
    cur.execute("""
        INSERT INTO ecommerce_bi.morning_report (report_date, content, anomalies)
        VALUES ('2014-12-17',
            '今日 DAU 11,962（环比 -1.1%），总订单 8,720 单。全站转化率 3.9%。',
            '[]')
    """)

    cur.execute("""
        INSERT INTO ecommerce_bi.recommends (user_id, item_id, score, reason) VALUES
        (1, 312051294, 0.95, '相似用户中78%购买了此商品'),
        (1, 232431562, 0.88, '与您经常浏览的商品同属数码品类'),
        (2, 100234567, 0.82, '同类商品中热度最高')
    """)
    conn.commit()

    # 验证
    cur.execute("SELECT COUNT(*) FROM ecommerce_bi.morning_report")
    report_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ecommerce_bi.recommends")
    recommend_count = cur.fetchone()[0]

    cur.execute("SELECT report_date, LEFT(content, 30) FROM ecommerce_bi.morning_report ORDER BY report_date DESC")
    reports = cur.fetchall()
    cur.execute("SELECT user_id, item_id, score FROM ecommerce_bi.recommends ORDER BY score DESC")
    recs = cur.fetchall()

    conn.close()

    print(f"[MySQL] OK (8.0) — {report_count} reports, {recommend_count} recommends")
    for r in reports:
        print(f"  report: {r[0]} | {r[1]}...")
    for r in recs:
        print(f"  recommend: user={r[0]} item={r[1]} score={r[2]}")
    return True


def test_hive():
    """Hive 连通性（需要 tier4_stu HiveServer2 已启动）"""
    from pyhive import hive
    try:
        conn = hive.Connection(
            host="localhost",
            port=10000,
            username="hive",
            database="default",
        )
        cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [row[0] for row in cur.fetchall()]
        conn.close()
        print(f"[Hive]  OK — databases: {dbs}")
        return True
    except Exception as e:
        print(f"[Hive]  NOT READY — {e}")
        print("  (HiveServer2 可能还在启动中，稍等 1-2 分钟后重试)")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("本地环境连通性测试")
    print("=" * 50)
    mysql_ok = test_mysql()
    hive_ok = test_hive()
    print("=" * 50)
    if mysql_ok and hive_ok:
        print("全部通过 — 可以运行 backend")
    elif mysql_ok:
        print("MySQL OK, Hive 待就绪 — Mock 模式可正常跑")
    else:
        print("部分不可用 — 检查 Docker 容器状态")
