"""
AI 数据洞察

输入 ADS 层 KPI 指标数据，调用 LLM 生成包含趋势解读、异常标注和业务建议的分析报告。

使用方式：
    from ai.insights import generate_insights

    kpi = {
        "date": "2014-12-18",
        "dau": 8230, "dau_change": 0.016,
        "total_orders": 3900, "orders_change": 0.03,
        "buy_conversion": 0.377, "conversion_change": 0.005,
        "avg_pv": 46.8,
    }

    report = generate_insights(kpi)
    print(report)
"""

import json
import sys
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.llm_client import get_llm_client

logger = logging.getLogger(__name__)

# ============================================================
# Prompt
# ============================================================

SYSTEM_PROMPT = """You are a senior e-commerce data analyst with 10 years of experience.
Your job is to analyze daily KPI metrics and generate concise, actionable insights in Chinese.

CONTEXT:
- Data is from a mobile e-commerce platform, period 2014-11-18 to 2014-12-18
- All metrics are at the platform level (aggregated from ~10,000 users, ~12 million behavior records)
- behavior_type: browse(浏览) → fav(收藏) → cart(加购) → buy(购买)

RULES:
1. Write in professional but accessible Chinese.
2. Structure your response in 3 parts:
   (a) 核心指标概览 - Summarize today's key numbers in 1-2 sentences.
   (b) 趋势与异常 - Point out any notable changes vs previous period. Flag metrics with >10% change as anomalies. If nothing abnormal, say "各指标平稳，无明显异常".
   (c) 运营建议 - 1-2 actionable suggestions based on the data. Be specific, not generic.

3. Keep the entire report to 150-300 Chinese characters.
4. Format numbers: use 万 for large numbers (e.g., 38.5万 not 385000).
5. Use percentages for ratios (e.g., 37.7% not 0.377).
6. Be honest: if data doesn't support a conclusion, don't fabricate one."""


# ============================================================
# 格式化
# ============================================================

def _format_kpi(kpi_data: dict) -> str:
    """将 KPI 字典格式化为 LLM 易读的文本"""
    lines = ["今日核心指标：", ""]

    # 格式化数值
    def fmt(val, is_pct=False):
        """智能格式化：百分数 vs 大数 vs 普通数"""
        if val is None:
            return "N/A"
        if isinstance(val, str):
            return val
        if is_pct:
            return f"{val * 100:.1f}%"
        if abs(val) >= 10000:
            return f"{val / 10000:.1f}万"
        return f"{val:,.0f}"

    field_map = {
        "date": ("日期", False),
        "dau": ("日活跃用户(DAU)", False),
        "dau_change": ("DAU环比变化", True),
        "total_pv": ("总浏览量(PV)", False),
        "pv_change": ("PV环比变化", True),
        "total_orders": ("订单量", False),
        "orders_change": ("订单量环比变化", True),
        "buy_conversion": ("购买转化率", True),
        "conversion_change": ("转化率环比变化", True),
        "avg_pv": ("人均PV", False),
        "avg_pv_change": ("人均PV环比变化", True),
    }

    for key, (label, is_pct) in field_map.items():
        if key in kpi_data:
            formatted = fmt(kpi_data[key], is_pct)
            lines.append(f"  {label}: {formatted}")

    return "\n".join(lines)


# ============================================================
# 公共接口
# ============================================================

def generate_insights(
    kpi_data: dict,
    extra_context: Optional[str] = None,
    temperature: float = 0.5,
) -> str:
    """
    基于 KPI 指标生成业务分析洞察。

    Args:
        kpi_data:     KPI 指标字典，支持 ads_daily_kpi 表的所有字段
        extra_context: 额外上下文（如 "今日发现数码品类流量异常下降"）
        temperature:   LLM 温度（0.5 兼顾创意和准确性）

    Returns:
        自然语言分析报告

    Example:
        >>> kpi = {"dau": 8230, "total_orders": 3900, "buy_conversion": 0.377}
        >>> report = generate_insights(kpi)
        >>> print(report)
        "今日DAU 8,230，订单量 3,900，转化率 37.7%。
         各项指标环比平稳，无明显异常。
         建议关注高转化品类，加大流量倾斜。"
    """
    llm = get_llm_client()

    kpi_text = _format_kpi(kpi_data)

    user_prompt = f"""以下是平台今日的核心指标数据：

{kpi_text}"""

    if extra_context:
        user_prompt += f"\n\n补充信息：{extra_context}"

    user_prompt += "\n\n请生成今日数据分析洞察："

    report = llm.chat(
        prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=temperature,
    )

    logger.info("Generated insights: input_keys=%d, report_len=%d",
                len(kpi_data), len(report))

    return report


# ============================================================
# 命令行测试
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    # 模拟 ads_daily_kpi 数据
    mock_kpi = {
        "date": "2014-12-18",
        "dau": 8230,
        "dau_change": 0.016,
        "total_pv": 385000,
        "pv_change": -0.02,
        "total_orders": 3900,
        "orders_change": 0.03,
        "buy_conversion": 0.377,
        "conversion_change": 0.005,
        "avg_pv": 46.8,
        "avg_pv_change": -0.01,
    }

    print("=" * 60)
    print("KPI Input:")
    print(json.dumps(mock_kpi, indent=2, ensure_ascii=False))
    print("=" * 60)
    print("\nAI Insights:\n")
    print(generate_insights(mock_kpi))
