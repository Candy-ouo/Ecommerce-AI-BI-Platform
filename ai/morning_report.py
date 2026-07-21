"""
AI 智能晨报

每日自动读取核心指标 → 环比 7 天前 → 识别 ±10% 异常 → LLM 生成 200-300 字晨报。

使用方式（C 的 scheduler.py 每日 8:00 调用）：
    from ai.morning_report import generate_report
    report = generate_report()
    # → {"date": "2014-12-18", "content": "...", "anomalies": [...]}

C 存入 MySQL 后，前端通过以下接口展示：
    GET /api/report/latest    → 最新晨报
    GET /api/report/history   → 历史晨报列表

前置依赖：
    ai.llm_client  — LLM 调用
    （可选）ai.agent.tools — 通过 C 的 API 拉取 KPI 数据
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.llm_client import get_llm_client

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

ANOMALY_THRESHOLD = 0.10  # ±10% 视为异常

SYSTEM_PROMPT = """# Role
You are the Chief Data Analyst at a mobile e-commerce company.
Every morning at 8:00 AM, you deliver a 3-minute read to the CEO and VP of Operations.
Your reports are trusted because they are: data-driven, concise, and always include actionable next steps.

# Context
- Platform: tianchi mobile e-commerce, 2014-11-18 to 2014-12-18
- Scale: ~10,000 users, ~12M behavior records, 31 days of data
- behavior funnel: 浏览(pv) → 收藏(fav) → 加购(cart) → 购买(buy)

# Reasoning (internal, do NOT output)
Before writing, mentally answer these 4 questions:
1. What is the single most important number the CEO needs to know?
2. Which metric change is most concerning (or encouraging)?
3. Is the anomaly a one-day blip or part of a trend?
4. What is ONE thing the operations team should do TODAY?

# Output Format — STRICT
Write in Chinese. Exactly 3 labeled sections, 200-350 characters total:

(a) 核心指标概览
Yesterday's headline numbers in 1-2 sentences. Start with the most impactful metric.

(b) 异常预警
List only metrics with >10% change vs 7 days ago. Format: "{指标名}{上升/下降}{X}%（{今日值} vs 7天前{对比值}）"
If no anomalies: "各指标环比波动均在正常范围内（±10%），无明显异常。"

(c) 运营建议
1-2 SPECIFIC actions. Include: what to do, on which segment, expected impact.
Bad example: "需要关注转化率下降" (too vague)
Good example: "对近3天加购未支付用户推送限时优惠券，预计可挽回15-20%流失订单"

# Constraints
- Every number must come from the input data — never fabricate.
- Do NOT repeat the full data table.
- If the data suggests conflicting signals, acknowledge uncertainty.
- No fluff phrases like "综上所述" or "我们将持续关注"."""



# ============================================================
# 异常检测
# ============================================================

def _detect_anomalies(today: dict, compare: dict) -> list:
    """
    对比今日和对比日指标，标记 >10% 变化的异常。

    Args:
        today:   今日 KPI
        compare: 对比日 KPI（7天前）

    Returns:
        [{metric, label, today_value, compare_value, change_pct}, ...]
    """
    anomalies = []

    metrics = [
        ("dau", "DAU", False),
        ("orders", "订单量", False),
        ("conversion_rate", "转化率", True),
        ("avg_pv", "人均PV", False),
    ]

    for key, label, is_rate in metrics:
        today_val = today.get(key)
        compare_val = compare.get(key)
        if today_val is None or compare_val is None or compare_val == 0:
            continue

        change = (today_val - compare_val) / compare_val

        if abs(change) >= ANOMALY_THRESHOLD:
            direction = "上升" if change > 0 else "下降"
            if is_rate:
                change_str = f"{change * 100:+.1f}个百分点"
                today_str = f"{today_val * 100:.1f}%"
                compare_str = f"{compare_val * 100:.1f}%"
            else:
                change_str = f"{change * 100:+.1f}%"
                today_str = f"{today_val:,.0f}"
                compare_str = f"{compare_val:,.0f}"

            anomalies.append({
                "metric": key,
                "label": label,
                "today_value": today_val,
                "compare_value": compare_val,
                "change_pct": round(change, 4),
                "description": f"{label}{direction}（{today_str} vs 7天前{compare_str}，{change_str}）",
            })

    return anomalies


# ============================================================
# 主入口
# ============================================================

def generate_report(
    today_kpi: Optional[dict] = None,
    compare_kpi: Optional[dict] = None,
) -> dict:
    """
    生成每日 AI 晨报。

    Args:
        today_kpi:   今日 KPI 数据（不传则尝试从 C 的 API 拉取）
        compare_kpi: 7 天前 KPI 数据（同上）

    Returns:
        {
            "date": "2014-12-18",
            "content": "晨报正文...",
            "anomalies": [...]
        }

    C 的 scheduler.py 调用示例：
        from ai.morning_report import generate_report
        report = generate_report()
        db.save_report(report)  # 存 MySQL
    """
    llm = get_llm_client()

    # 尝试从 C 的 API 拉取数据
    if today_kpi is None:
        try:
            from ai.agent.tools import get_daily_kpi
            today_kpi = get_daily_kpi()
            if "error" in today_kpi:
                logger.warning("Cannot fetch KPI from API: %s", today_kpi["error"])
                today_kpi = _mock_today_kpi()
        except Exception as e:
            logger.warning("Cannot import tools: %s, using mock", e)
            today_kpi = _mock_today_kpi()

    if compare_kpi is None:
        compare_kpi = _mock_compare_kpi()

    # 异常检测
    anomalies = _detect_anomalies(today_kpi, compare_kpi)

    # 构建 Prompt
    if anomalies:
        anomaly_lines = "\n".join([f"  - {a['description']}" for a in anomalies])
    else:
        anomaly_lines = "（无，各指标变化均在 ±10% 以内）"

    user_prompt = f"""## Yesterday ({today_kpi.get('date', 'N/A')}) vs 7 Days Ago ({compare_kpi.get('date', 'N/A')})

| Metric | Yesterday | 7 Days Ago | Change |
|--------|-----------|------------|--------|
| DAU | {today_kpi.get('dau', 'N/A'):,} | {compare_kpi.get('dau', 'N/A'):,} | {_fmt_change(today_kpi, compare_kpi, 'dau')} |
| Orders | {today_kpi.get('orders', 'N/A'):,} | {compare_kpi.get('orders', 'N/A'):,} | {_fmt_change(today_kpi, compare_kpi, 'orders')} |
| Conversion Rate | {today_kpi.get('conversion_rate', 0)*100:.1f}% | {compare_kpi.get('conversion_rate', 0)*100:.1f}% | {_fmt_change_pct(today_kpi, compare_kpi, 'conversion_rate')} |
| Avg PV/User | {today_kpi.get('avg_pv', 'N/A')} | {compare_kpi.get('avg_pv', 'N/A')} | {_fmt_change(today_kpi, compare_kpi, 'avg_pv')} |

## Pre-detected Anomalies (>10% change)
{anomaly_lines}

Write the morning report:"""

    content = llm.chat(prompt=user_prompt, system_prompt=SYSTEM_PROMPT, temperature=0.5)

    report = {
        "date": today_kpi.get("date", "N/A"),
        "content": content,
        "anomalies": [a["description"] for a in anomalies],
    }

    logger.info("Morning report generated: date=%s, len=%d, anomalies=%d",
                report["date"], len(content), len(anomalies))

    return report


# ============================================================
# 辅助
# ============================================================

def _fmt_change(today: dict, compare: dict, key: str) -> str:
    """格式化环比变化"""
    tv = today.get(key)
    cv = compare.get(key)
    if tv is None or cv is None or cv == 0:
        return "N/A"
    change = (tv - cv) / cv
    return f"{change * 100:+.1f}% ({tv:,.0f} vs {cv:,.0f})"


def _fmt_change_pct(today: dict, compare: dict, key: str) -> str:
    """格式化百分比类环比变化"""
    tv = today.get(key)
    cv = compare.get(key)
    if tv is None or cv is None or cv == 0:
        return "N/A"
    change = (tv - cv) / cv
    return f"{change * 100:+.1f}% ({tv * 100:.1f}% vs {cv * 100:.1f}%)"


def _mock_today_kpi() -> dict:
    return {
        "date": "2014-12-18",
        "dau": 8230, "dau_change": 0.016,
        "orders": 3900, "conversion_rate": 0.377, "avg_pv": 46.8,
    }


def _mock_compare_kpi() -> dict:
    return {
        "date": "2014-12-11",
        "dau": 8100, "dau_change": 0.01,
        "orders": 3700, "conversion_rate": 0.380, "avg_pv": 48.2,
    }


# ============================================================
# 命令行测试
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    print("=" * 60)
    print("AI Morning Report Generator")
    print("=" * 60)

    report = generate_report()

    print(f"\nDate: {report['date']}")
    print(f"Anomalies ({len(report['anomalies'])}):")
    for a in report["anomalies"]:
        print(f"  - {a}")
    print(f"\nReport:\n{report['content']}")
