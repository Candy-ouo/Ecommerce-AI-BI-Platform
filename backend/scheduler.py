"""定时任务调度器：每天 8:00 触发 AI 晨报生成。

接 B 的 ai.morning_report.generate_report() 生成晨报，落库到 MySQL
morning_report 表，D 通过 /api/report/* 展示。

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

# 报告变更事件订阅者（SSE 推送用，由 report.py 注册）
_report_subscribers: list = []


def subscribe_report(callback):
    """注册报告变更监听（供 report.py 的 SSE 端点用）。"""
    _report_subscribers.append(callback)


def _notify_subscribers(report: dict):
    """通知所有 SSE 订阅者。"""
    for cb in _report_subscribers:
        try:
            cb(report)
        except Exception:
            pass


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

        # 推送
        _push_dingtalk(report)
        _notify_subscribers(report)

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
