"""定时任务调度器：每天 8:00 触发 AI 晨报生成。

流程：调用 api.report.trigger_report_generation() → Hive 取数 → LLM 生成 → 入内存缓存 → SSE 推送。

生成成功后：
- 钉钉推送（如配置了 DINGTALK_WEBHOOK）
- 唤醒 SSE 报告流（通知在线的 D 前端）
"""
import json
import logging
from datetime import datetime

import requests

from config import USE_REAL_DATA

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _push_dingtalk(report: dict):
    """通过钉钉机器人 Webhook 推送晨报。

    Args:
        report: {date, content, anomalies} 字典
    """
    from config import DINGTALK_WEBHOOK

    webhook = DINGTALK_WEBHOOK
    if not webhook:
        logger.debug("DINGTALK_WEBHOOK 未配置，跳过推送")
        return

    anomaly_text = "\n".join(
        f"- {a}" for a in (report.get("anomalies") or [])
    ) or "（无异常）"

    md = (
        f"## 📊 AI 智能晨报 — {report.get('date', '')}\n\n"
        f"{report.get('content', '')}\n\n"
        f"### ⚠️ 异常预警\n{anomaly_text}"
    )

    payload = {"msgtype": "markdown", "markdown": {"title": f"AI晨报 {report.get('date', '')}", "text": md}}

    try:
        r = requests.post(webhook, json=payload, timeout=10)
        if r.status_code == 200:
            logger.info("钉钉晨报推送成功")
        else:
            logger.warning("钉钉推送异常 HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.error("钉钉推送失败: %s", e)


def _generate_daily_report():
    """每日晨报生成任务（每天 8:00 触发）。

    调用 api.report.trigger_report_generation()：
    从 Hive 取数 → LLM 生成 → 入内存缓存 → SSE 推送订阅者。
    不再依赖 MySQL / services.db。
    """
    logger.info("晨报生成任务触发 — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    if not USE_REAL_DATA:
        logger.info("晨报生成 Mock：USE_REAL_DATA=false，仅打日志")
        return

    try:
        from api.report import trigger_report_generation

        report = trigger_report_generation()
        logger.info("晨报生成成功 — %s", report.get("date", ""))

        # 钉钉推送
        _push_dingtalk(report)

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
