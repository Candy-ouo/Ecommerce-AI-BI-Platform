"""POST /api/agent/analyze —— ReAct Agent 多步数据分析，SSE 流式输出。

与 chat.py 区别：
  - chat: NL2SQL 单次查询（适合"XX商品销量？"）
  - agent: ReAct 循环调用 5 个 API 工具，综合生成分析报告（适合"全面分析XX"）
"""
import json
import logging
import os
import sys

from flask import Blueprint, request, Response, stream_with_context

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

bp = Blueprint("agent", __name__, url_prefix="/api/agent")
logger = logging.getLogger(__name__)

_run_agent = None


def _lazy_import():
    global _run_agent
    if _run_agent is None:
        try:
            from ai.agent.analysis_agent import run_agent
            _run_agent = run_agent
            logger.info("Agent 模块加载成功")
        except Exception as e:
            logger.warning("Agent 模块加载失败: %s", e)


@bp.route("/analyze", methods=["POST"])
def analyze():
    """Agent 分析入口（SSE 流式）。

    POST /api/agent/analyze
    Body: {"task": "帮我分析一下最近的用户转化情况"}
    Returns: SSE stream
    """
    data = request.get_json(silent=True) or {}
    task = (data.get("task", "")
            or data.get("question", "")
            or data.get("message", "") or "").strip()

    if not task:
        def _empty():
            yield _sse({"type": "text", "content": "请提供分析任务描述。"})
            yield _sse({"type": "done"})
        return Response(stream_with_context(_empty()), mimetype="text/event-stream")

    def generate():
        _lazy_import()
        if not _run_agent:
            yield _sse({"type": "text", "content": "Agent 模块未就绪，请检查 LLM 配置。"})
            yield _sse({"type": "done"})
            return

        yield _sse({"type": "text", "content": f"正在分析：{task[:50]}...\n\n"})

        try:
            report = _run_agent(task)
            # 后处理：Agent 可能返回 JSON 格式 {"action":"final","answer":"..."}
            # 尝试提取纯文本 answer，失败则保留原文
            try:
                parsed = json.loads(report)
                if isinstance(parsed, dict) and "answer" in parsed:
                    report = parsed["answer"]
            except (json.JSONDecodeError, TypeError):
                pass
            logger.info("Agent 报告长度: %d 字符", len(report))
            # 流式推送报告（每 15 个字一块，减少碎片）
            for i in range(0, len(report), 15):
                yield _sse({"type": "text", "content": report[i:i + 15]})
        except Exception as e:
            logger.error("Agent 执行异常: %s", e)
            yield _sse({"type": "text", "content": f"分析过程出错：{e}"})

        yield _sse({"type": "done"})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
