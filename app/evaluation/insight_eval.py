"""洞察 Agent 评测器 —— Insight 维度跑分（sql_accuracy / chart_success_rate / interpretation_readability）。

三项指标都在**确定性、离线**面评测（无 LLM、无 DB、无 Milvus）：
- **sql_accuracy**：NL2SQL 安全收口 `assert_safe_sql` 的判定准确率（安全 SQL 放行 + 危险 SQL 拦截）。
  这是不依赖 LLM 即可评的「SQL 层」正确性，直接背书「三层数据隔离」声明；端到端生成准确率
  （LLM 直出 SQL 是否正确）留 W09 以注入式 generator 接入。
- **chart_success_rate**：`rows_to_chart` 能产出可渲染图表（非 noData、有 series + type）的比例。
- **interpretation_readability**：洞察文本的确定性可读性启发式（分段 / 含数字 / 有建议 / 长度合理）。

只 import `assert_safe_sql` / `rows_to_chart`（均已被现有 CI 测试导入）+ metrics，保持 CI-light。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.data_insight.echarts import rows_to_chart
from app.agents.data_insight.nl2sql import assert_safe_sql
from app.evaluation.metrics import InsightMetric

_ADVICE_KEYWORDS = ("建议", "推荐", "注意", "可以")


@dataclass(frozen=True)
class SqlCase:
    sql: str
    user_id: str
    expected_safe: bool


@dataclass(frozen=True)
class ChartCase:
    rows: list[dict]
    question: str


def _is_safe(sql: str, user_id: str) -> bool:
    try:
        assert_safe_sql(sql, user_id)
    except ValueError:
        return False
    return True


def sql_accuracy(cases: list[SqlCase]) -> float:
    """安全收口判定准确率：gate 的放行 / 拦截与标注一致的比例。"""
    if not cases:
        return 0.0
    correct = sum(_is_safe(c.sql, c.user_id) == c.expected_safe for c in cases)
    return correct / len(cases)


def _chart_ok(chart: dict) -> bool:
    if chart.get("noData"):
        return False
    series = chart.get("series") or []
    return bool(series) and bool(series[0].get("type"))


def chart_success_rate(cases: list[ChartCase]) -> float:
    if not cases:
        return 0.0
    ok = sum(_chart_ok(rows_to_chart(c.rows, c.question)) for c in cases)
    return ok / len(cases)


def readability_score(text: str) -> float:
    """洞察文本可读性启发式 ∈ [0,1]：长度合理 / 分段 / 含数字 / 有建议。"""
    text = (text or "").strip()
    if not text:
        return 0.0
    checks = (
        len(text) >= 40,                                  # 不过短
        len(text) <= 1200,                                # 不过长（4 段式洞察上限）
        text.count("\n") >= 2,                            # 多段结构
        bool(re.search(r"\d", text)),                     # 数据落地（含数字）
        any(k in text for k in _ADVICE_KEYWORDS),         # 有可执行建议
    )
    return sum(checks) / len(checks)


def interpretation_readability(texts: list[str]) -> float:
    if not texts:
        return 0.0
    return sum(readability_score(t) for t in texts) / len(texts)


# —— 内置 gold 集 ——
GOLD_SQL_CASES: list[SqlCase] = [
    SqlCase("SELECT date, weight_kg FROM vitals WHERE user_id = 'u1' ORDER BY date DESC", "u1", True),
    SqlCase("SELECT date, protein FROM daily_intake WHERE user_id = 'u1' LIMIT 30", "u1", True),
    SqlCase("UPDATE vitals SET weight_kg=0 WHERE user_id='u1'", "u1", False),          # 非 SELECT
    SqlCase("SELECT 1 FROM vitals WHERE user_id='u1'; DROP TABLE vitals;", "u1", False),  # 多语句
    SqlCase("SELECT date FROM vitals", "u1", False),                                   # 缺 user_id
    SqlCase("SELECT * FROM admin_secrets WHERE user_id='u1'", "u1", False),            # 非授权表
    SqlCase("DELETE FROM daily_intake WHERE user_id='u1'", "u1", False),               # 禁用词
    SqlCase("SELECT * FROM vitals JOIN users u ON u.id=vitals.user_id WHERE user_id='u1'", "u1", False),  # JOIN 非授权表
]

GOLD_CHART_CASES: list[ChartCase] = [
    ChartCase([{"date": "2026-05-01", "protein": 80}, {"date": "2026-05-02", "protein": 82}], "近30天蛋白质趋势"),
    ChartCase([{"meal": "早餐", "kcal": 500}, {"meal": "午餐", "kcal": 700}], "每餐热量"),
    ChartCase([{"碳水": 260, "蛋白质": 80, "脂肪": 65}], "三大产能营养素占比"),
]

# 代表性洞察文本（4 段式：概览 / 达标 / 异常 / 建议），供可读性评分演示。
GOLD_INSIGHT_TEXTS: list[str] = [
    "本次数据共 30 条。\n近 30 天日均蛋白质 78g，接近推荐的 80g。\n"
    "有 6 天低于 60g，集中在周末。\n建议周末增加一份鸡蛋或鱼类，把蛋白质补到 80g 以上。",
    "近 7 天日均饮水 1850ml，低于 2000ml 推荐线。\n"
    "周三、周四明显偏低（<1500ml）。\n建议在工位放置水杯定时提醒，注意餐前补水。",
]


def evaluate_insight(
    sql_cases: list[SqlCase] | None = None,
    chart_cases: list[ChartCase] | None = None,
    insight_texts: list[str] | None = None,
) -> InsightMetric:
    return InsightMetric(
        sql_accuracy=sql_accuracy(sql_cases if sql_cases is not None else GOLD_SQL_CASES),
        chart_success_rate=chart_success_rate(
            chart_cases if chart_cases is not None else GOLD_CHART_CASES
        ),
        interpretation_readability=interpretation_readability(
            insight_texts if insight_texts is not None else GOLD_INSIGHT_TEXTS
        ),
    )


def main() -> None:
    import json

    from app.evaluation.metrics import aggregate_dashboard

    print(json.dumps(aggregate_dashboard(evaluate_insight()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
