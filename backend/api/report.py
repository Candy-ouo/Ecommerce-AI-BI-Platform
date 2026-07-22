"""AI 晨报接口 —— 直读 Hive，调 LLM 生成，内存缓存。

端点：
  POST /api/report/generate   — 手动触发晨报生成（scheduler 或按钮调用）
  GET  /api/report/latest     — 最新一期晨报（缓存 → 兜底实时生成）
  GET  /api/report/history?days=N  — 历史晨报列表（默认 7 天，从内存缓存取）
  GET  /api/report/stream     — SSE 实时推送（大屏长连接）

数据源：
  ads_daily_kpi   (最近 8 天 → 今日 + 7 天前环比)
  ads_funnel      (最新 1 条全站漏斗)
  ads_category_topn (最新 Top3 热度类目)

依赖：services.hive_client.query()、ai.llm_client、scheduler 订阅机制。
不再依赖 services.db (MySQL)。
"""
import json
import queue
import logging
from datetime import date, timedelta
from threading import Lock

from flask import Blueprint, request, Response, stream_with_context

from api._response import ok, fail
from config import USE_REAL_DATA

bp = Blueprint("report", __name__, url_prefix="/api/report")
logger = logging.getLogger(__name__)

# ── 内存缓存 ──────────────────────────────────────
_report_cache: list[dict] = []
_report_lock = Lock()

# ── SSE 订阅者列表 ──────────────────────────────────
_report_subscribers: list = []


def subscribe_report(callback):
    """注册报告变更监听（供 report.py 的 SSE 端点用）。"""
    _report_subscribers.append(callback)


def unsubscribe_report(callback):
    """取消注册（SSE 客户端断开时清理）。"""
    try:
        _report_subscribers.remove(callback)
    except ValueError:
        pass


def _notify_subscribers(report: dict):
    """通知所有 SSE 订阅者。"""
    for cb in _report_subscribers:
        try:
            cb(report)
        except Exception:
            pass


def _add_to_cache(report: dict):
    """将新报告插入缓存（最新在前，同日期覆盖，上限 30 条）。"""
    with _report_lock:
        for i, r in enumerate(_report_cache):
            if r.get("date") == report.get("date"):
                _report_cache[i] = report
                return
        _report_cache.insert(0, report)
        if len(_report_cache) > 30:
            _report_cache.pop()


# ── Hive 查询 ──────────────────────────────────────

def _query_hive_kpi() -> dict:
    """从 ads_daily_kpi 取最近 8 天 → 返回 {today: row, compare: row|None}。"""
    from services.hive_client import query

    sql = """
        SELECT dt, dau, dau_change, total_pv, pv_change,
               total_orders, orders_change, buy_conversion, conversion_change,
               avg_pv, avg_pv_change
        FROM ads_daily_kpi
        ORDER BY dt DESC
        LIMIT 8
    """
    df = query(sql)
    if df.empty:
        return {"today": None, "compare": None}

    rows = df.to_dict("records")
    today = rows[0]
    today_dt = str(today["dt"])
    target_dt = (date.fromisoformat(today_dt) - timedelta(days=7)).isoformat()

    compare = None
    for r in rows:
        if str(r["dt"]) == target_dt:
            compare = r
            break
    if compare is None and len(rows) >= 8:
        compare = rows[-1]

    return {"today": today, "compare": compare}


def _query_hive_funnel() -> dict | None:
    """从 ads_funnel 取最新一条全站漏斗（item_category IS NULL）。"""
    from services.hive_client import query

    sql = """
        SELECT dt, level_name, pv_users, fav_users, cart_users, buy_users,
               pv_to_fav_rate, fav_to_cart_rate, cart_to_buy_rate, pv_to_buy_rate
        FROM ads_funnel
        WHERE item_category IS NULL
        ORDER BY dt DESC
        LIMIT 1
    """
    df = query(sql)
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def _query_hive_category_topn(limit: int = 3) -> list[dict]:
    """从 ads_category_topn 取最新日期的 TopN 类目（按 pv_rank 升序）。"""
    from services.hive_client import query

    sql = f"""
        SELECT dt, item_category, pv_cnt, buy_cnt, uv, buy_conversion, pv_rank, buy_rank
        FROM ads_category_topn
        ORDER BY dt DESC, pv_rank ASC
        LIMIT {limit}
    """
    df = query(sql)
    if df.empty:
        return []
    return df.to_dict("records")


# ── 数据 → 文本拼装 ────────────────────────────────

def _num(val, fmt=",.0f"):
    """安全格式化数值（兼容 pandas/numpy 类型）。"""
    if val is None:
        return "N/A"
    try:
        return f"{float(val):{fmt}}"
    except (ValueError, TypeError):
        return "N/A"


def _pct(val):
    """将小数转为百分比字符串（如 0.042 → '4.2%'）。"""
    if val is None:
        return "N/A"
    try:
        return f"{float(val) * 100:.1f}%"
    except (ValueError, TypeError):
        return "N/A"


def _calc_change(today_val, compare_val) -> str:
    """计算环比变化百分比。"""
    if today_val is None or compare_val is None:
        return "N/A"
    try:
        tv, cv = float(today_val), float(compare_val)
        if cv == 0:
            return "N/A"
        change = (tv - cv) / cv
        return f"{change * 100:+.1f}%"
    except (ValueError, TypeError):
        return "N/A"


def _build_prompt(kpi_data: dict, funnel: dict | None, categories: list[dict]) -> str:
    """将 Hive 数据拼成 LLM 可读的 Markdown 表格。"""
    today = kpi_data.get("today") or {}
    compare = kpi_data.get("compare") or {}

    lines = []

    # ── KPI 指标表 ──
    lines.append("## 核心 KPI 指标")
    today_dt = str(today.get("dt", "N/A"))
    compare_dt = str(compare.get("dt", "N/A")) if compare else "N/A"
    lines.append(f"日期: {today_dt} vs 7天前: {compare_dt}")
    lines.append("")
    lines.append("| 指标 | 今日 | 7天前 | 环比变化 |")
    lines.append("|------|------|-------|----------|")

    kpi_rows = [
        ("DAU",              "dau",          _num),
        ("全站PV",           "total_pv",     _num),
        ("订单量",           "total_orders", _num),
        ("购买转化率",        "buy_conversion", _pct),
        ("人均PV",           "avg_pv",       _num),
    ]
    for label, key, fmt_fn in kpi_rows:
        t_str = fmt_fn(today.get(key))
        c_str = fmt_fn(compare.get(key)) if compare else "N/A"
        chg = _calc_change(today.get(key), compare.get(key) if compare else None)
        lines.append(f"| {label} | {t_str} | {c_str} | {chg} |")
    lines.append("")

    # ── 漏斗数据 ──
    if funnel:
        lines.append("## 全站转化漏斗")
        lines.append(f"日期: {funnel.get('dt', 'N/A')}")
        lines.append(f"- 浏览用户: {_num(funnel.get('pv_users'))}")
        lines.append(f"- 收藏用户: {_num(funnel.get('fav_users'))}  → 浏览→收藏率: {_pct(funnel.get('pv_to_fav_rate'))}")
        lines.append(f"- 加购用户: {_num(funnel.get('cart_users'))} → 收藏→加购率: {_pct(funnel.get('fav_to_cart_rate'))}")
        lines.append(f"- 购买用户: {_num(funnel.get('buy_users'))} → 加购→购买率: {_pct(funnel.get('cart_to_buy_rate'))}")
        lines.append(f"- 整体浏览→购买转化率: {_pct(funnel.get('pv_to_buy_rate'))}")
        lines.append("")

    # ── Top3 类目 ──
    if categories:
        lines.append("## 类目热度 Top3")
        for i, cat in enumerate(categories):
            lines.append(
                f"{i + 1}. 类目{cat.get('item_category')}: "
                f"PV {_num(cat.get('pv_cnt'))}, "
                f"购买 {_num(cat.get('buy_cnt'))}, "
                f"转化率 {_pct(cat.get('buy_conversion'))}"
            )
        lines.append("")

    return "\n".join(lines)


# ── 异常检测 ──────────────────────────────────────

def _detect_anomalies(kpi_data: dict) -> list[str]:
    """从 Hive KPI 数据中自动检测环比变化超过 ±10% 的指标。"""
    today = kpi_data.get("today") or {}
    compare = kpi_data.get("compare") or {}
    if not today or not compare:
        return []

    anomalies = []
    checks = [
        ("dau",           "DAU"),
        ("total_pv",      "全站PV"),
        ("total_orders",   "订单量"),
        ("buy_conversion", "购买转化率"),
        ("avg_pv",         "人均PV"),
    ]

    for key, label in checks:
        try:
            tv = float(today.get(key))
            cv = float(compare.get(key))
        except (TypeError, ValueError):
            continue
        if cv == 0:
            continue

        change = (tv - cv) / cv
        if abs(change) >= 0.10:
            direction = "上升" if change > 0 else "下降"
            if key == "buy_conversion":
                desc = (
                    f"{label} {direction} {change * 100:+.1f}个百分点"
                    f"（{tv * 100:.1f}% vs 7天前{cv * 100:.1f}%）"
                )
            else:
                desc = (
                    f"{label} {direction} {change * 100:+.1f}%"
                    f"（{tv:,.0f} vs 7天前{cv:,.0f}）"
                )
            anomalies.append(desc)

    return anomalies


# ── LLM 调用 ──────────────────────────────────────

SYSTEM_PROMPT = """# 角色
你是一家手机电商的首席数据策略师。每天早上 8:00，你向 CEO 和运营副总裁提交一份 3 分钟晨报。
你的报告以数据驱动、逻辑清晰、建议可落地而深受信任。

# 背景
- 平台：天池手机电商，时间 2014-11-18 至 2014-12-18
- 规模：约 10,000 用户，~1200 万条行为记录
- 用户行为路径：浏览 → 收藏 → 加购 → 购买

# 要求
- 基于提供的指标数据，计算 7 日环比变化
- 识别变化幅度超过 ±10% 的指标作为异常预警
- 给出 1-2 条可执行的运营建议（明确做什么、针对谁、预期效果）

# 输出格式（严格遵循，200-300 字中文）
(a) 核心指标概览
用 1-2 句话概括昨日最重要的指标表现。

(b) 异常预警
仅列出环比变化超过 ±10% 的指标。
格式："{指标名} {上升/下降} {X}%（{今日值} vs 7天前{对比值}）"
如无异常："各指标环比波动均在正常范围内（±10%），无明显异常。"

(c) 运营建议
1-2 条具体动作。

# 约束
- 所有数字必须来自输入数据，禁止编造
- 不要输出"综上所述""我们将持续关注"等套话
- 中文输出"""


def _call_llm(data_text: str) -> str:
    """调 LLM 生成晨报正文。"""
    from ai.llm_client import get_llm_client
    llm = get_llm_client()
    user_prompt = f"{data_text}\n\n请根据以上数据生成今日晨报："
    return llm.chat(
        prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=0.5,
        max_tokens=800,
    ).strip()


# ── 核心生成逻辑（供 scheduler 和 API 共用）───────

def trigger_report_generation() -> dict:
    """从 Hive 取数 → LLM 生成 → 入缓存 → 推送 SSE → 返回报告。

    scheduler.py 每天 8:00 直接调用此函数，无需走 HTTP。
    """
    if not USE_REAL_DATA:
        report = _mock_report()
        _add_to_cache(report)
        _notify_subscribers(report)
        logger.info("Mock 晨报生成完成: date=%s", report["date"])
        return report

    # 1. 查 Hive
    kpi_data = _query_hive_kpi()
    funnel = _query_hive_funnel()
    categories = _query_hive_category_topn(3)

    if not kpi_data.get("today"):
        raise RuntimeError("ads_daily_kpi 无数据，请先运行 ETL")

    # 2. 拼 prompt + 调 LLM
    prompt_text = _build_prompt(kpi_data, funnel, categories)
    logger.info("晨报 prompt 长度: %d 字符", len(prompt_text))

    content = _call_llm(prompt_text)

    # 3. 异常检测
    anomalies = _detect_anomalies(kpi_data)

    report = {
        "date": str(kpi_data["today"]["dt"]),
        "content": content,
        "anomalies": anomalies,
    }

    # 4. 入缓存 + 推送 SSE
    _add_to_cache(report)
    _notify_subscribers(report)
    logger.info(
        "晨报生成成功: date=%s, len=%d, anomalies=%d",
        report["date"], len(content), len(anomalies),
    )

    return report


# ── Mock ──────────────────────────────────────────

def _mock_report() -> dict:
    return {
        "date": "2014-12-18",
        "content": (
            "今日 DAU 12,345（环比 +3.2%），总订单 8,900 单。"
            "全站转化率 4.2%，较昨日提升 0.3 个百分点。"
            "数码品类表现突出，浏览量环比增长 15%，购买转化率达 5.8%。"
            "建议关注服饰品类的收藏加购率下降趋势。"
        ),
        "anomalies": ["数码品类销量增长 15%", "服饰品类收藏率下降 5%"],
    }


def _mock_history(days: int) -> list[dict]:
    data = [
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
    ]
    return data[:days]


# ── API 端点 ──────────────────────────────────────

@bp.route("/generate", methods=["POST"])
def generate():
    """手动触发晨报生成。"""
    try:
        report = trigger_report_generation()
        return ok(report)
    except Exception as e:
        logger.error("晨报生成失败: %s", e, exc_info=True)
        return fail(f"晨报生成失败: {e}")


@bp.route("/latest")
def latest():
    """最新一期晨报。缓存有则直接返回，无则实时生成。"""
    if not USE_REAL_DATA:
        return ok(_mock_report())

    with _report_lock:
        if _report_cache:
            return ok(_report_cache[0])

    # 缓存为空 → 兜底实时生成
    try:
        report = trigger_report_generation()
        return ok(report)
    except Exception as e:
        return fail(f"晨报生成失败: {e}")


@bp.route("/history")
def history():
    """历史晨报列表（从内存缓存取，最新在前）。"""
    days = request.args.get("days", 7, type=int)

    if not USE_REAL_DATA:
        return ok(_mock_history(days))

    with _report_lock:
        return ok(_report_cache[:days])


@bp.route("/stream")
def stream():
    """SSE 实时晨报推送端点。

    大屏打开后建立长连接，新报告生成时自动推送，无需轮询。
    每 30 秒心跳保活。
    """
    def generate():
        q: queue.Queue = queue.Queue()

        def on_new_report(report):
            q.put_nowait(report)

        subscribe_report(on_new_report)

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
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        except GeneratorExit:
            unsubscribe_report(on_new_report)
            logger.info("SSE report stream client disconnected")

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
