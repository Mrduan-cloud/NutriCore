"""洞察评测器单测 —— 守住 sql_accuracy / chart_success_rate / interpretation_readability 的正确性。

要点：
- gold 集上三项应 = 1.0。
- 但指标要**能识别退化**：削弱安全守卫的判定 → sql_accuracy 掉；坏数据 → chart 失败；
  空 / 干瘪文本 → 可读性低。
"""
from app.evaluation.insight_eval import (
    GOLD_CHART_CASES,
    GOLD_INSIGHT_TEXTS,
    GOLD_SQL_CASES,
    ChartCase,
    SqlCase,
    chart_success_rate,
    evaluate_insight,
    interpretation_readability,
    readability_score,
    sql_accuracy,
)
from app.evaluation.metrics import aggregate_dashboard


def test_gold_sql_accuracy_is_perfect():
    """安全收口在 2 安全 + 6 危险用例上判定全对 → 1.0（回归守护）。"""
    assert sql_accuracy(GOLD_SQL_CASES) == 1.0


def test_gold_chart_success_is_perfect():
    assert chart_success_rate(GOLD_CHART_CASES) == 1.0


def test_gold_insight_readability_is_perfect():
    assert interpretation_readability(GOLD_INSIGHT_TEXTS) == 1.0


def test_sql_accuracy_detects_misclassification():
    """**关键**：把一条危险 SQL 标成 safe，gate 仍会拦 → 判定不一致 → 准确率掉。"""
    bad = [SqlCase("DROP TABLE vitals", "u1", expected_safe=True)]
    assert sql_accuracy(bad) == 0.0


def test_chart_success_rate_drops_on_bad_data():
    """空数据 / 无数值列 → noData → 不算成功。"""
    cases = [
        ChartCase([], "近30天趋势"),                       # 空
        ChartCase([{"label": "x"}], "随便画"),              # 无数值列
    ]
    assert chart_success_rate(cases) == 0.0


def test_readability_score_discriminates():
    empty = readability_score("")
    thin = readability_score("数据看完了")  # 过短、无数字、无分段、无建议
    good = readability_score(GOLD_INSIGHT_TEXTS[0])
    assert empty == 0.0
    assert thin < good
    assert good == 1.0


def test_readability_rewards_numbers_and_advice():
    """含数字 + 建议 + 分段的文本，应高于缺这些要素的同长文本。"""
    rich = "近 30 天日均蛋白质 78g。\n有 6 天偏低。\n建议补充优质蛋白到 80g。"
    plain = "蛋白质摄入情况整体看起来还算可以但是没有给出任何可执行的下一步指引说明文字"
    assert readability_score(rich) > readability_score(plain)


def test_evaluate_insight_full_gold():
    m = evaluate_insight()
    assert m.sql_accuracy == 1.0
    assert m.chart_success_rate == 1.0
    assert m.interpretation_readability == 1.0


def test_empty_inputs_zero_not_crash():
    assert sql_accuracy([]) == 0.0
    assert chart_success_rate([]) == 0.0
    assert interpretation_readability([]) == 0.0


def test_dashboard_aggregation_shape():
    dash = aggregate_dashboard(evaluate_insight())
    assert set(dash["InsightMetric"]) == {
        "sql_accuracy", "chart_success_rate", "interpretation_readability",
    }
