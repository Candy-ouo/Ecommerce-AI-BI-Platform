"""GET /api/report/latest + GET /api/report/history + GET /api/report/stream —— AI 晨报接口。

Real 模式：读 MySQL 中 B 的 morning_report.py 产出的晨报表。
USE_REAL_DATA=false 或不具备连接时返回 Mock。

GET /api/report/stream —— SSE 实时推送晨报（供 D 大屏长连接）。
  当日 8:00 scheduler 生成新晨报后自动推送，无需轮询。
"""
import json
import queue
import logging

from flask import Blueprint, request, Response, stream_with_context

from api._response import ok, fail
from config import USE_REAL_DATA
from services.db import get_report_latest, get_report_history
from scheduler import subscribe_report, unsubscribe_report

bp = Blueprint("report", __name__, url_prefix="/api/report")
logger = logging.getLogger(__name__)


@bp.route("/latest")
def latest():
    if USE_REAL_DATA:
        try:
            row = get_report_latest()
            if row is None:
                return fail("no report yet", 404)
            return ok({
                "date": str(row["report_date"]),
                "content": row["content"],
                "anomalies": _parse_anomalies(row.get("anomalies")),
            })
        except Exception as e:
            return fail(str(e))

    return ok({
        "date": "2014-12-18",
        "content": (
            "今日 DAU 12,345（环比 +3.2%），总订单 8,900 单。"
            "全站转化率 4.2%，较昨日提升 0.3 个百分点。"
            "数码品类表现突出，浏览量环比增长 15%，购买转化率达 5.8%。"
            "建议关注服饰品类的收藏加购率下降趋势。"
        ),
        "anomalies": ["数码品类销量增长 15%", "服饰品类收藏率下降 5%"],
    })


@bp.route("/history")
def history():
    days = request.args.get("days", 7, type=int)

    if USE_REAL_DATA:
        try:
            rows = get_report_history(days)
            reports = [
                {
                    "date": str(r["report_date"]),
                    "content": r["content"],
                    "anomalies": _parse_anomalies(r.get("anomalies")),
                }
                for r in rows
            ]
            return ok(reports)
        except Exception as e:
            return fail(str(e))

    return ok([
        {
            "date": "2014-12-18",
            "content": "今日 DAU 12,345（环比 +3.2%），总订单 8,900 单。全站转化率 4.2%。",
            "anomalies": ["数码品类销量增长 15%"],
        },
        {
            "date": "2014-12-17",
            "content": "今日 DAU 11,962（环比 -1.1%），总订单 8,720 单。全站转化率 3.9%。",
            "anomalies": [],
        },
        {
            "date": "2014-12-16",
            "content": "今日 DAU 12,100（环比 +2.5%），总订单 9,050 单。全站转化率 4.1%。",
            "anomalies": ["服饰品类购买转化下降 8%"],
        },
    ][:days])


@bp.route("/stream")
def stream():
    """SSE 实时晨报推送端点。

    长连接：大屏打开后建立此连接，scheduler 生成新晨报时自动推送。
    事件格式：data: {"type":"report","date":"...","content":"...","anomalies":[...]}

    每 30 秒发一次心跳（ping）保活。
    """
    def generate():
        q: queue.Queue = queue.Queue()

        def on_new_report(report):
            q.put_nowait(report)

        subscribe_report(on_new_report)

        # 心跳间隔
        import time as _time
        heartbeat_interval = 30

        try:
            while True:
                try:
                    report = q.get(timeout=heartbeat_interval)
                    payload = json.dumps({
                        "type": "report",
                        "date": report.get("date", ""),
                        "content": report.get("content", ""),
                        "anomalies": report.get("anomalies", []),
                    }, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                except queue.Empty:
                    # 心跳保活
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        except GeneratorExit:
            unsubscribe_report(on_new_report)
            logger.info("SSE report stream client disconnected")

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",        # 禁用 nginx 缓冲
        },
    )


def _parse_anomalies(raw):
    """将 MySQL 中存储的 anomalies（可能是 JSON 字符串或逗号分隔）转为列表。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    import json
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [s.strip() for s in str(raw).split(",") if s.strip()]
