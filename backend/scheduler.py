"""定时任务调度器：每天 8:00 触发 AI 晨报生成。

接 B 的 ai.morning_report.generate_report() 生成晨报，落库到 MySQL
morning_report 表，D 通过 /api/report/* 展示。
"""
import logging
from datetime import datetime

from config import USE_REAL_DATA

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _generate_daily_report():
    """每日晨报生成任务（每天 8:00 触发）。"""
    logger.info("晨报生成任务触发 — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    if not USE_REAL_DATA:
        logger.info("晨报生成 Mock：USE_REAL_DATA=false，仅打日志")
        return

    try:
        # B 的 AI 晨报模块
        from ai.morning_report import generate_report
        from services.db import save_report

        report = generate_report()
        save_report(report["date"], report["content"], report["anomalies"])
        logger.info("晨报生成成功 — %s", report.get("date", ""))
    except Exception as e:
        logger.error("晨报生成失败: %s", e)


def start_scheduler():
    """启动定时任务调度器（在 app.py 中调用）。"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("apscheduler 未安装，跳过定时任务启动。安装：pip install apscheduler")
        return None

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _generate_daily_report,
        trigger="cron",
        hour=8,
        minute=0,
        id="daily_morning_report",
        name="每日 AI 晨报生成",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("定时任务调度器已启动 | 每日 8:00 触发晨报生成")
    return scheduler
