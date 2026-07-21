"""定时任务调度器：每天 8:00 触发 AI 晨报生成。

当前为框架模式（Mock），等 B 的 morning_report.py 就绪后，
取消 _generate_daily_report() 中的注释，接真实生成逻辑。
"""
import logging
from datetime import datetime

from config import USE_REAL_DATA

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _generate_daily_report():
    """每日晨报生成任务（每天 8:00 触发）。"""
    logger.info("晨报生成任务触发 — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    if USE_REAL_DATA:
        # TODO: 等 B 的 morning_report.py 就绪后接入
        #   from ai.morning_report import generate_report
        #   report = generate_report()
        #   # 报告内容由 B 的模块自行存入 MySQL，C 不在此重复写库
        #   logger.info("晨报生成成功 — %s", report.get("date", ""))
        #   return report
        logger.warning("晨报生成：USE_REAL_DATA=true 但 B 模块未接入，跳过")
    else:
        logger.info("晨报生成 Mock：数据开关关闭，仅打日志")


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
