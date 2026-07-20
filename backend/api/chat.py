"""POST /api/chat —— AI 对话（SSE 流式）。

当前是 Mock 流式输出，演示 SSE 形状（text 分片 → chart 事件 → done）。
Day 2 下午接入 B 的 AI 模块后，把 generate_sql / result_explainer / run_agent
串进来即可（见下方 TODO）。
"""
import json
import time

from flask import Blueprint, request, Response, stream_with_context

bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@bp.route("", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    # TODO(Day2 下午): 接入 B 的 AI 模块
    # from ai.nl2sql.sql_generator import generate_sql
    # from ai.nl2sql.result_explainer import explain_result
    # from ai.agent.analysis_agent import run_agent
    # from services.hive_client import query
    #
    # # 方案1：NL2SQL 流程
    # result = generate_sql(message)          # → {sql, raw}
    # df = query(result["sql"])               # → DataFrame
    # answer = explain_result(message, result["sql"], df)
    # # 方案2：Agent 流程
    # # answer = run_agent(message)

    def generate():
        # Mock：把回复切成小段逐字推送（text 事件）
        reply = (f"【Mock】收到：{message}。"
                 f"等 B 的 AI 模块接入后，这里会返回真实数据分析。")
        for i in range(0, len(reply), 6):
            chunk = reply[i:i + 6]
            yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
            time.sleep(0.05)

        # Mock：演示 chart 事件（真实场景由 B 的模块决定何时发图表）
        yield f"data: {json.dumps({'type': 'chart', 'chartType': 'bar',
                                   'data': {'x': ['浏览', '收藏', '加购', '购买'],
                                            'y': [100000, 35000, 20000, 8000]}},
                                  ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")
