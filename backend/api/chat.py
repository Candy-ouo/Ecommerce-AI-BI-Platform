"""POST /api/chat —— AI 对话（SSE 流式），支持多轮对话上下文。

接入 B 的 NL2SQL 模块：自然语言 → generate_sql → query(Hive) → explain_result → SSE 流式输出。
若 B 模块不可用或 USE_REAL_DATA=false，自动降级为 Mock 流式。

多轮对话：
  请求体中传 session_id（可选），后端复用该会话的对话历史（最多保留 10 轮）。
  前端首次请求无需传 session_id，后端自动生成并返回在 done 事件中。
"""
import json
import logging
import os
import sys
import time
import threading
import traceback
import uuid
from collections import defaultdict, deque

import pandas as pd
from flask import Blueprint, request, Response, stream_with_context

from config import USE_REAL_DATA

# B 的 ai/ 模块在项目根目录，需要加到 Python 路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

bp = Blueprint("chat", __name__, url_prefix="/api/chat")
logger = logging.getLogger(__name__)


# ── IP 频率限制（防刷 LLM 费用）────────────────
_rate_limit_store: dict = defaultdict(list)
_RATE_MAX = 10       # 每分钟最多 10 次
_RATE_WINDOW = 60    # 窗口 60 秒


def _check_rate_limit(ip: str, max_requests: int = _RATE_MAX, window: int = _RATE_WINDOW) -> bool:
    """基于 IP 的滑动窗口限流。返回 True 表示放行，False 触发限流。"""
    now = time.time()
    bucket = _rate_limit_store[ip]
    while bucket and bucket[0] < now - window:
        bucket.pop(0)
    if len(bucket) >= max_requests:
        return False
    bucket.append(now)
    return True


# ── 会话上下文存储（内存，进程重启后丢失；生产可替换为 Redis）──
_MAX_HISTORY = 10          # 每会话最多保留 10 轮（Q+A）
_SESSION_TTL = 3600        # 会话 1 小时无活动自动过期（秒）
_sessions: dict = defaultdict(lambda: deque(maxlen=_MAX_HISTORY * 2))
_session_lock = threading.Lock()


def _get_session_history(session_id: str) -> list:
    """获取会话对话历史（列表形式，元素为 {role, content}）。"""
    with _session_lock:
        return list(_sessions.get(session_id, []))


def _append_session(session_id: str, role: str, content: str):
    """追加一条消息到会话历史。"""
    with _session_lock:
        _sessions[session_id].append({"role": role, "content": content})


def _cleanup_expired_sessions():
    """清理过期会话（简化版：每次新会话时惰性清理）。"""
    # 基于内存 dict，暂无精确 TTL 清除；会话数通常很少（10 并发），影响可忽略。
    pass


# ── 延迟导入 B 模块（避免 import 阶段炸掉整个 app）──
_generate_sql = None
_explain_result = None
_smart_chat = None
_query = None

def _lazy_import():
    """惰性加载 B 模块 + C 的 hive_client。失败则留 None，chat() 自动降级 Mock。"""
    global _generate_sql, _explain_result, _smart_chat, _query
    if _generate_sql is None:
        try:
            from ai.nl2sql.sql_generator import generate_sql as gs
            _generate_sql = gs
        except Exception:
            logger.warning("sql_generator 不可用: %s", traceback.format_exc())
    if _smart_chat is None:
        try:
            from ai.nl2sql.sql_generator import smart_chat as sc
            _smart_chat = sc
        except Exception:
            logger.warning("smart_chat 不可用: %s", traceback.format_exc())
    if _explain_result is None:
        try:
            from ai.nl2sql.result_explainer import explain_result as er
            _explain_result = er
        except Exception:
            logger.warning("result_explainer 不可用: %s", traceback.format_exc())
    if _query is None:
        try:
            from services.hive_client import query as q
            _query = q
        except Exception:
            logger.warning("hive_client 不可用: %s", traceback.format_exc())


def _build_context_message(message: str, session_id: str) -> str:
    """将对话历史注入当前问题，构建带上下文的提示。

    格式：将前几轮 Q&A 拼成对话摘录，最后附当前问题。
    """
    if not session_id:
        return message

    history = _get_session_history(session_id)
    if len(history) < 2:
        return message

    context_lines = ["以下是之前的对话摘录（供上下文参考，不要重复之前的回答）："]
    for h in history[-8:]:                       # 只取最近 4 轮（8 条）
        role_cn = "用户" if h["role"] == "user" else "助手"
        content = h["content"][:200]             # 截断长回答
        context_lines.append(f"{role_cn}: {content}")

    context_lines.append(f"用户（当前问题）: {message}")
    return "\n".join(context_lines)


@bp.route("", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    # 兼容 D 前端发送 {question} 和旧版 {message} 两种字段名
    message = (data.get("message", "") or data.get("question", "") or "").strip()
    session_id = (data.get("session_id", "") or "").strip() or str(uuid.uuid4())[:8]

    if not message:
        def _empty():
            yield f"data: {json.dumps({'type': 'text', 'content': '请输入您的问题。'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        return Response(stream_with_context(_empty()), mimetype="text/event-stream")

    # 频率限制
    client_ip = request.remote_addr or "127.0.0.1"
    if not _check_rate_limit(client_ip):
        def _rate_limited():
            yield f"data: {json.dumps({'type': 'text', 'content': '请求过于频繁，请稍后再试。'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        return Response(stream_with_context(_rate_limited()), mimetype="text/event-stream")

    # 多轮对话：将之前对话上下文化
    contextual_message = _build_context_message(message, session_id)

    def generate():
        # 记录用户消息
        _append_session(session_id, "user", message)

        # ── 走真实 NL2SQL（B 的 smart_chat 混合模式）──
        if USE_REAL_DATA:
            _lazy_import()
            if _smart_chat and _query and _explain_result:
                try:
                    # 1. B 的混合路由：意图分类 + SQL 生成/闲聊/知识问答
                    sc_result = _smart_chat(contextual_message)

                    # 2. 非数据查询 → 直接返回文本
                    if sc_result.get("type") != "data_query":
                        reply = sc_result.get("answer", "抱歉，我无法回答这个问题。")
                        _append_session(session_id, "assistant", reply)
                        for i in range(0, len(reply), 10):
                            yield f"data: {json.dumps({'type': 'text', 'content': reply[i:i+10]}, ensure_ascii=False)}\n\n"
                            time.sleep(0.03)
                        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
                        return

                    # 3. 数据查询：执行 SQL + 解读（兼容 smart_chat 只返回 sql）
                    sql = sc_result.get("sql", "")
                    if not sql or sql == "UNABLE_TO_ANSWER":
                        reply = "抱歉，我目前只能回答数据分析相关的问题。"
                        _append_session(session_id, "assistant", reply)
                        yield f"data: {json.dumps({'type': 'text', 'content': reply}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
                        return

                    yield f"data: {json.dumps({'type': 'text', 'content': '正在查询数据...'}, ensure_ascii=False)}\n\n"
                    df = _query(sql)
                    answer = _explain_result(contextual_message, sql, df)
                    _append_session(session_id, "assistant", answer)
                    yield f"data: {json.dumps({'type': 'text', 'content': answer}, ensure_ascii=False)}\n\n"

                    chart = _df_to_chart(df)
                    if chart:
                        yield f"data: {json.dumps({'type': 'chart', **chart}, ensure_ascii=False)}\n\n"

                    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
                    return

                except Exception as e:
                    logger.error("NL2SQL 链路异常: %s", traceback.format_exc())
                    reply = f"分析出错：{e}"
                    _append_session(session_id, "assistant", reply)
                    yield f"data: {json.dumps({'type': 'text', 'content': reply}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
                    return

            # ── smart_chat 不可用但 generate_sql 可用时降级 ──
            if _generate_sql and _query and _explain_result:
                try:
                    result = _generate_sql(contextual_message)
                    if result.get("sql") == "UNABLE_TO_ANSWER":
                        reply = "抱歉，我目前只能回答数据分析相关的问题。"
                        _append_session(session_id, "assistant", reply)
                        yield f"data: {json.dumps({'type': 'text', 'content': reply}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
                        return
                    yield f"data: {json.dumps({'type': 'text', 'content': '正在查询数据...'}, ensure_ascii=False)}\n\n"
                    df = _query(result["sql"])
                    answer = _explain_result(contextual_message, result["sql"], df)
                    _append_session(session_id, "assistant", answer)
                    yield f"data: {json.dumps({'type': 'text', 'content': answer}, ensure_ascii=False)}\n\n"
                    chart = _df_to_chart(df)
                    if chart:
                        yield f"data: {json.dumps({'type': 'chart', **chart}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
                    return
                except Exception as e:
                    logger.error("NL2SQL 降级链路异常: %s", traceback.format_exc())
                    reply = f"分析出错：{e}"
                    _append_session(session_id, "assistant", reply)
                    yield f"data: {json.dumps({'type': 'text', 'content': reply}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
                    return

        # ── Mock 降级（D 前端 ai_chat.js 的 mockSend 自己处理 Mock chart，C 只给 text+done）──
        reply = f"【Mock】收到：{message}。等 B 的 AI 模块接入后，这里会返回真实数据分析。"
        _append_session(session_id, "assistant", reply)
        for i in range(0, len(reply), 6):
            chunk = reply[i:i + 6]
            yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
            time.sleep(0.05)

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


def _df_to_chart(df):
    """把 SQL 结果 DataFrame 转成 chart 事件（对齐 D 前端 ai_chat.js buildChartOption）。

    返回格式：{chartType, data: {categories, values}} 或 {chartType, data: {labels, counts}}（饼图）
    自动推断：行数≤5且2列且首列非数值 → pie；行数>8 → line；其他 → bar。
    """
    if df is None or getattr(df, "empty", True) or len(df.columns) < 2:
        return None
    cols = list(df.columns)
    categories = [str(v) for v in df[cols[0]].tolist()[:20]]
    for c in cols[1:]:
        if pd.api.types.is_numeric_dtype(df[c]):
            values = [float(v) if pd.notna(v) else 0.0 for v in df[c].tolist()[:20]]
            # 饼图：类别少 + 首列为标签名 → pie
            if len(values) <= 5 and not pd.api.types.is_numeric_dtype(df[cols[0]]):
                return {
                    "chartType": "pie",
                    "data": {"labels": categories, "counts": values},
                }
            chart_type = "line" if len(values) > 8 else "bar"
            return {
                "chartType": chart_type,
                "data": {"categories": categories, "values": values},
            }
    return None
