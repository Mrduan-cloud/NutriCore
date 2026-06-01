"""筛查评测器单测 —— 守住「评测集 + 跑分器」的正确性，而非只看分数。

要点：
- 实现必须 100% 符合金标准（确定性评分 → accuracy/completeness/consistency 应 = 1.0）。
- 但 accuracy 指标本身要**能识别偏离**（不是平凡恒 1.0）—— 用一条故意标错的用例验证它会掉到 < 1.0。
"""
from app.agents.risk_screening.nrs2002 import compute_nrs2002
from app.agents.risk_screening.schemas import NRSAnswer
from app.evaluation.metrics import aggregate_dashboard
from app.evaluation.screening_eval import (
    GOLD_CASES,
    GoldCase,
    _scoring_signature,
    evaluate_screening,
    score_accuracy,
)


def test_gold_set_score_accuracy_is_perfect():
    """实现符合临床金标准 → 准确率 1.0。任何偏离都会让它掉下来（回归守护）。"""
    assert evaluate_screening(GOLD_CASES).score_accuracy == 1.0


def test_gold_set_completeness_is_perfect():
    assert evaluate_screening(GOLD_CASES).report_completeness == 1.0


def test_retest_consistency_is_perfect():
    """确定性评分多次跑签名恒一致 → 复测一致率 1.0。"""
    assert evaluate_screening(GOLD_CASES).retest_consistency == 1.0


def test_accuracy_metric_detects_divergence():
    """**关键**：故意标错的用例必须把准确率拉低，证明指标不是平凡恒 1.0。"""
    mislabeled = [
        GoldCase("wrong", NRSAnswer(age=30, bmi=22), expected_total=3, expected_level="有营养风险"),
    ]
    assert score_accuracy(mislabeled) == 0.0


def test_consistency_signature_excludes_timestamp():
    """同输入两次评分：answered_at 时间戳可不同，但评分签名必须一致。"""
    a = NRSAnswer(age=30, bmi=22)
    r1, r2 = compute_nrs2002("u", a), compute_nrs2002("u", a)
    assert _scoring_signature(r1) == _scoring_signature(r2)


def test_gold_set_covers_both_risk_outcomes():
    """好的评测集不能单一类别 —— 二分两种结局都要有。"""
    levels = {c.expected_level for c in GOLD_CASES}
    assert levels == {"暂无营养风险", "有营养风险"}
    assert len(GOLD_CASES) >= 12


def test_all_metrics_in_unit_range():
    m = evaluate_screening(GOLD_CASES)
    for v in (m.score_accuracy, m.report_completeness, m.retest_consistency):
        assert 0.0 <= v <= 1.0


def test_empty_cases_yield_zero_not_crash():
    m = evaluate_screening([])
    assert (m.score_accuracy, m.report_completeness, m.retest_consistency) == (0.0, 0.0, 0.0)


def test_dashboard_aggregation_shape():
    dash = aggregate_dashboard(evaluate_screening(GOLD_CASES))
    assert "ScreeningMetric" in dash
    assert set(dash["ScreeningMetric"]) == {
        "score_accuracy", "report_completeness", "retest_consistency",
    }
