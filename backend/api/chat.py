"""POST /api/chat —— AI 对话（SSE 流式）。

接入 B 的 NL2SQL 模块：自然语言 → generate_sql → query(Hive) → explain_result → SSE 流式输出。
若 B 模块不可用或 USE_REAL_DATA=false，自动降级为 Mock 流式。
"""
import json
import logging
import os
import sys
import time
import traceback

import pandas as pd
from flask import Blueprint, request, Response, stream_with_context

from config import USE_REAL_DATA

# B 的 ai/ 模块在项目根目录，需要加到 Python 路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

bp = Blueprint("chat", __name__, url_prefix="/api/chat")
logger = logging.getLogger(__name__)


# ── 延迟导入 B 模块（避免 import 阶段炸掉整个 app）──
_generate_sql = None
_explain_result = None
_query = None

def _lazy_import():
    """惰性加载 B 模块 + C 的 hive_client。失败则留 None，chat() 自动降级 Mock。"""
    global _generate_sql, _explain_result, _query
    if _generate_sql is None:
        try:
            from ai.nl2sql.sql_generator import generate_sql as gs
            _generate_sql = gs
        except Exception:
            logger.warning("sql_generator 不可用: %s", traceback.format_exc())
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


@bp.route("", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message", "") or "").strip()

    if not message:
        def _empty():
            yield f"data: {json.dumps({'type': 'text', 'content': '请输入您的问题。'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        return Response(stream_with_context(_empty()), mimetype="text/event-stream")

    def generate():
        # ── 走真实 NL2SQL ──
        if USE_REAL_DATA:
            _lazy_import()
            if _generate_sql and _query and _explain_result:
                try:
                    # 1. NL → SQL
                    result = _generate_sql(message)

                    # 2. 安全拒绝
                    if result.get("sql") == "UNABLE_TO_ANSWER":
                        yield f"data: {json.dumps({'type': 'text', 'content': '抱歉，我目前只能回答数据分析相关的问题。'}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                        return

                    # 3. 执行 SQL
                    yield f"data: {json.dumps({'type': 'text', 'content': '正在查询数据...'}, ensure_ascii=False)}\n\n"
                    df = _query(result["sql"])

                    # 4. 解读结果
                    answer = _explain_result(message, result["sql"], df)
                    yield f"data: {json.dumps({'type': 'text', 'content': answer}, ensure_ascii=False)}\n\n"

                    # 5. 图表事件（SQL 结果为表结构时附带）
                    chart = _df_to_chart(df)
                    if chart:
                        yield f"data: {json.dumps({'type': 'chart', **chart}, ensure_ascii=False)}\n\n"

                    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    return

                except Exception as e:
                    logger.error("NL2SQL 链路异常: %s", traceback.format_exc())
                    yield f"data: {json.dumps({'type': 'text', 'content': f'分析出错：{e}'}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    return

        # ── Mock 降级 ──
        reply = f"【Mock】收到：{message}。等 B 的 AI 模块接入后，这里会返回真实数据分析。"
        for i in range(0, len(reply), 6):
            chunk = reply[i:i + 6]
            yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
            time.sleep(0.05)

        # Mock 图表事件（满足前端 chart 契约）
        chart = {
            "chartType": "bar",
            "title": "示例图表（Mock）",
            "x": ["A", "B", "C", "D"],
            "y": [120, 200, 150, 80],
            "xLabel": "类别",
            "yLabel": "数值",
        }
        yield f"data: {json.dumps({'type': 'chart', **chart}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


def _df_to_chart(df):
    """把 SQL 结果 DataFrame 转成 chart 事件数据（取首列作 x，首个数值列作 y）。"""
    if df is None or getattr(df, "empty", True) or len(df.columns) < 2:
        return None
    cols = list(df.columns)
    x = [str(v) for v in df[cols[0]].tolist()[:20]]
    for c in cols[1:]:
        if pd.api.types.is_numeric_dtype(df[c]):
            y = [float(v) for v in df[c].tolist()[:20]]
            return {
                "chartType": "bar",
                "title": "查询结果",
                "x": x,
                "y": y,
                "xLabel": str(cols[0]),
                "yLabel": str(c),
            }
    return None
