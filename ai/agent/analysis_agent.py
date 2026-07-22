"""
AI Agent — 多步数据分析任务编排

实现 ReAct 风格的 Agent 循环：LLM 规划 → 调用工具 → 获取数据 → 继续或输出最终报告。
不依赖 LangChain，纯 Prompt + 工具执行循环。

使用方式（C 在 chat.py 中可选调用）：
    from ai.agent.analysis_agent import run_agent
    report = run_agent("帮我分析最近一周的用户转化情况")

前置依赖：
    ai.llm_client       — LLM 调用
    ai.agent.tools      — 5 个工具函数
"""

import json
import re
import sys
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai.llm_client import get_llm_client
from ai.agent.tools import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5  # 最多执行 5 轮工具调用

# ============================================================
# Agent System Prompt
# ============================================================

SYSTEM_PROMPT = """# Role
You are a Senior E-commerce Data Analyst with 10 years of experience.
You investigate business questions by gathering data step-by-step, then writing an executive summary.
Rule #1: NEVER answer without data. ALWAYS call at least one tool first.

# Context
- Platform: tianchi mobile e-commerce, 2014-11-18 to 2014-12-18
- Scale: ~10K users, ~12M behavior records
- Funnel: 浏览(pv) → 收藏(fav) → 加购(cart) → 购买(buy)
- Note: Current data is Mock mode — treat numbers as demonstration

# Available Tools
| Tool | When to Use | Args |
|------|-------------|------|
| get_daily_kpi | Overall health check: DAU, orders, conversion | None |
| get_active_trend | Time-series questions: "trend", "变化", "最近N天" | days (int, default 7) |
| get_top_items | Ranking questions: "top", "热门", "最高", "排行" | limit (int), sort_by (pv/fav/buy) |
| get_funnel | Conversion questions: "漏斗", "转化", "流失" | None |
| get_rfm_distribution | User segmentation: "用户分层", "价值分布", "RFM" | None |

# Tool Selection Strategy (internal reasoning)
Before calling a tool, ask yourself:
- Does the task mention "trend" or "变化"? → get_active_trend first
- Does it mention "转化" or "漏斗"? → get_funnel first
- Does it mention "用户" + "价值/分层/分布"? → get_rfm_distribution first
- Is it a general "分析"/"看下情况"? → get_daily_kpi first, then decide if you need more

# Protocol — EXACT output format
Each turn, output ONE JSON object. No other text, no markdown.

Tool call:
{"action": "tool_call", "tool": "get_funnel", "args": {}}

Final report (after >=1 tool call):
{"action": "final", "answer": "Your report..."}

# Report Quality Standards
Your final report should be:
1. Data-driven — Every claim backed by numbers from tool results
2. Structured — Overview first, then drill-down, then actionable insight
3. Concise — 6-12 sentences in Chinese
4. Actionable — End with 1-2 specific recommendations
5. Readable — Use line breaks (\\n) to separate paragraphs. Put 2-3 sentences per paragraph. Do not output one giant wall of text.
6. End with a "你可以继续追问：" line followed by 3 short suggested questions, each ending with ？. Keep them concise.

Good example: "全站转化漏斗显示，浏览→收藏转化率35%，但收藏→加购仅57%。\\n\\n建议在收藏页增加'一键加购'按钮，以减少此环节流失。"
Bad example: "转化率需要关注。" (too vague, no data, no action)

# Edge Cases
- Tool returns error: try an alternative tool, or report the limitation honestly
- Data is Mock: acknowledge it's simulated, but still provide valid analysis logic
- Question is not analytics-related: respond with "抱歉，我只能回答数据分析相关问题。"""



# ============================================================
# 工具执行
# ============================================================

# 构建工具名 → 函数的快速查找表
_TOOL_MAP = {t["name"]: t["function"] for t in TOOL_DEFINITIONS}


def _execute_tool(tool_name: str, args: dict) -> dict:
    """执行单个工具调用，返回结果"""
    if tool_name not in _TOOL_MAP:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        fn = _TOOL_MAP[tool_name]
        if args:
            return fn(**args)
        return fn()
    except TypeError as e:
        # 参数不匹配时尝试无参调用
        logger.warning("Tool %s called with wrong args %s, retrying without args: %s", tool_name, args, e)
        return fn()
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 响应解析
# ============================================================

def _parse_llm_response(raw: str) -> dict:
    """从 LLM 返回中提取 JSON 动作（支持嵌套 {}）"""
    text = raw.strip()

    # 去掉可能包裹的 markdown 代码块
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    # 找第一个完整的 JSON 对象（括号计数，支持嵌套）
    start = text.find("{")
    if start == -1:
        return {"action": "final", "answer": raw}

    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end > start:
        json_str = text[start:end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # 解析失败 → 当作最终回答
    if len(raw) > 50:
        return {"action": "final", "answer": raw}
    return {"action": "final", "answer": "抱歉，分析过程出错，请重新描述您的需求。"}


# ============================================================
# Agent 主循环
# ============================================================

def run_agent(task: str) -> str:
    """
    执行 Agent 分析任务。

    Args:
        task: 用户的高层级分析任务，如 "帮我分析一下最近的用户转化情况"

    Returns:
        Agent 生成的中文分析报告
    """
    llm = get_llm_client()
    history = []  # 对话历史
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        logger.info("Agent iteration %d/%d", iteration, MAX_ITERATIONS)

        # 构建当前轮的 prompt
        history_text = "\n".join(history[-10:]) if history else "(no previous steps)"

        # 帮助 LLM 做工具选择的路标
        task_lower = task.lower()
        hints = []
        if any(w in task_lower for w in ["趋势", "变化", "走势", "最近"]):
            hints.append("Consider starting with get_active_trend")
        if any(w in task_lower for w in ["转化", "漏斗", "流失"]):
            hints.append("Consider starting with get_funnel")
        if any(w in task_lower for w in ["用户", "分层", "价值", "分布", "rfm"]):
            hints.append("Consider starting with get_rfm_distribution")
        if any(w in task_lower for w in ["排行", "热门", "top", "最高"]):
            hints.append("Consider starting with get_top_items")
        if not hints:
            hints.append("Start with get_daily_kpi for an overview, then decide")

        hint_text = "\n".join(f"  → {h}" for h in hints)

        user_prompt = f"""## Task
{task}

## Strategy Hint
{hint_text}

## Previous Steps
{history_text}

## Now
Output ONE JSON: {{"action":"tool_call","tool":"...","args":{{...}}}} or {{"action":"final","answer":"..."}}"""

        raw = llm.chat(prompt=user_prompt, system_prompt=SYSTEM_PROMPT, temperature=0.1)
        logger.debug("LLM raw (%d chars): %s", len(raw), raw[:300])
        parsed = _parse_llm_response(raw)

        logger.info("Agent action: %s → %s", parsed.get("action", "unknown"),
                    str(parsed.get("answer", parsed.get("tool", "")))[:80])

        # 最终回答
        if parsed.get("action") == "final":
            answer = parsed.get("answer", "")
            logger.info("Agent finished: answer_len=%d", len(answer))
            return answer

        # 工具调用
        if parsed.get("action") == "tool_call":
            tool_name = parsed.get("tool", "")
            args = parsed.get("args", {})

            if not tool_name:
                history.append(f"[Error] No tool name specified in: {raw[:200]}")
                continue

            result = _execute_tool(tool_name, args)
            result_str = json.dumps(result, ensure_ascii=False, indent=2)

            history.append(f"Called {tool_name}({args}) → result: {result_str[:500]}")
            logger.info("  Tool: %s(%s) → %d chars", tool_name, args, len(result_str))
            continue

        # 无法识别的动作 → 当作最终回答
        logger.warning("Unrecognized action, treating as final: %s", raw[:100])
        return raw

    # 达到最大迭代数 → 强制 LLM 生成最终报告
    logger.warning("Max iterations reached, forcing final answer")
    force_prompt = f"You have made {MAX_ITERATIONS} tool calls. Based on the results below, provide a final Chinese analysis report.\n\n" + "\n".join(history)
    final = llm.chat(prompt=force_prompt, system_prompt=SYSTEM_PROMPT)
    return final


# ============================================================
# 命令行测试
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    tasks = [
        "帮我分析一下最近的用户转化情况",
        "看看用户价值分布，判断是否需要做用户召回",
    ]

    for task in tasks:
        print(f"\n{'='*60}")
        print(f"Task: {task}")
        print(f"{'='*60}")
        report = run_agent(task)
        print(f"\nAgent Report:\n{report}")
