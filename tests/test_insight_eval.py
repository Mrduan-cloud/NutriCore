"""洞察评测器单测 —— 守住 sql_accuracy / chart_success_rate / interpretation_readability 的正确性。

要点：
- gold 集上三项应 = 1.0。
- 但指标要**能识别退化**：削弱安全守卫的判定 → sql_accuracy 掉；坏数据 → chart 失败；
  空 / 干瘪文本 → 可读性低。
"""
import pytest

from app.evaluation.insight_eval import (
    GOLD_CHART_CASES,
    GOLD_INSIGHT_TEXTS,
    GOLD_SQL_CASES,
    GOLD_SQL_GEN_CASES,
    ChartCase,
    SqlCase,
    SqlGenCase,
    chart_success_rate,
    end_to_end_sql_accuracy,
    evaluate_insight,
    interpretation_readability,
    readability_score,
    replay_generator,
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
    assert end_to_end_sql_accuracy([], lambda q, u: "SELECT 1") == 0.0


# —— 端到端 NL2SQL 评测（注入式，CI 用 stub 验证打分逻辑）——


def test_e2e_perfect_with_replay_stub():
    """gold 的 ideal_sql 全部既安全又命中期望表/列 → 1.0（回归守护）。"""
    gen = replay_generator(GOLD_SQL_GEN_CASES)
    assert end_to_end_sql_accuracy(GOLD_SQL_GEN_CASES, gen) == 1.0


def test_e2e_detects_wrong_table():
    """**关键**：generator 答错了表（蛋白质问题却查 vitals）→ 命中失败 → 分数掉。"""
    case = SqlGenCase("最近30天蛋白质", "u1",
                      frozenset({"daily_intake"}), frozenset({"protein"}))

    def wrong(q, u):
        return "SELECT date, steps FROM vitals WHERE user_id = 'u1'"

    assert end_to_end_sql_accuracy([case], wrong) == 0.0


def test_e2e_detects_missing_field():
    """安全且表对，但漏了关键字段（问蛋白质却只选 date）→ 不算答对。"""
    case = SqlGenCase("蛋白质摄入", "u1",
                      frozenset({"daily_intake"}), frozenset({"protein"}))

    def miss(q, u):
        return "SELECT date FROM daily_intake WHERE user_id = 'u1'"

    assert end_to_end_sql_accuracy([case], miss) == 0.0


def test_e2e_counts_unsafe_as_failure():
    """generator 直出越权 / 危险 SQL（无 user_id 过滤）→ 过不了 gate → 端到端失败。"""
    case = SqlGenCase("所有人的体重", "u1",
                      frozenset({"vitals"}), frozenset({"weight_kg"}))

    def unsafe(q, u):
        return "SELECT weight_kg FROM vitals"  # 缺 user_id 强制过滤

    assert end_to_end_sql_accuracy([case], unsafe) == 0.0


def test_e2e_propagates_backend_error_not_silent_zero():
    """（/debug #1）后端连不上等非 ValueError **向上抛**，不静默成 0.0——
    让 dashboard live 能区分「模型答错」与「后端不可用」并回落，看板分数不骗人。"""
    case = GOLD_SQL_GEN_CASES[0]

    def backend_down(q, u):
        raise ConnectionError("LLM backend unreachable")

    with pytest.raises(ConnectionError):
        end_to_end_sql_accuracy([case], backend_down)


def test_e2e_partial_credit_across_cases():
    """两条用例，一条答对一条答错 → 0.5（指标按用例平均，不是全 0/1）。"""
    good = GOLD_SQL_GEN_CASES[0]  # ideal_sql 选了 protein → 命中
    bad = SqlGenCase(
        "另一个问题", "u1", frozenset({"daily_intake"}), frozenset({"protein"}),
        ideal_sql="SELECT date FROM daily_intake WHERE user_id='u1'",  # 漏 protein → 不命中
    )
    cases = [good, bad]
    assert end_to_end_sql_accuracy(cases, replay_generator(cases)) == 0.5


def test_evaluate_insight_offline_skips_e2e():
    """不注入 generator → e2e 记 0.0；前三项仍离线算出。"""
    m = evaluate_insight()
    assert m.e2e_sql_accuracy == 0.0
    assert m.sql_accuracy == 1.0


def test_evaluate_insight_with_injected_generator():
    m = evaluate_insight(sql_generator=replay_generator(GOLD_SQL_GEN_CASES))
    assert m.e2e_sql_accuracy == 1.0


def test_dashboard_aggregation_shape():
    dash = aggregate_dashboard(evaluate_insight())
    assert set(dash["InsightMetric"]) == {
        "sql_accuracy", "chart_success_rate", "interpretation_readability",
        "e2e_sql_accuracy",
    }
