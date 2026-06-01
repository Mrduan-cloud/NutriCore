"""筛查 Agent 评测器 —— 把 metrics.py 的指标容器接上真实跑分。

评测对象：NRS-2002 确定性评分链路 (`compute_nrs2002`)。
金标准评测集 `GOLD_CASES` 按 ESPEN 2002 (Kondrup) 临床判定标准**独立标注**，
因此本评测同时是「实现是否符合临床规则」的回归守护——评分逻辑一旦偏离金标准，
`score_accuracy` 立刻 < 1.0。

三个指标（对应 `ScreeningMetric`）：
- **score_accuracy**：计算 total_score + risk_level 同时命中金标准的比例。
- **report_completeness**：报告必填字段齐全（分值在合法区间 + 建议非空 + 风险等级合法）的比例。
- **retest_consistency**：同一输入多次评分得到**相同评分签名**的比例（确定性应 = 1.0）；
  签名刻意排除非确定性的 `answered_at` 时间戳。

纯确定性、离线可跑，纳入 CI。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.risk_screening.nrs2002 import compute_nrs2002
from app.agents.risk_screening.schemas import DiseaseSeverity, NRSAnswer, NRSReport
from app.evaluation.metrics import ScreeningMetric

_VALID_LEVELS = {"暂无营养风险", "有营养风险"}


@dataclass(frozen=True)
class GoldCase:
    """一条金标准用例：输入 + 期望 total_score + 期望风险等级（人工按临床标准标注）。"""

    case_id: str
    answer: NRSAnswer
    expected_total: int
    expected_level: str


def _case(case_id: str, expected_total: int, expected_level: str, **answer_kwargs) -> GoldCase:
    return GoldCase(case_id, NRSAnswer(**answer_kwargs), expected_total, expected_level)


# 16 例金标准，覆盖各计分维度 + 二分边界 + 两个历史回归点。
GOLD_CASES: list[GoldCase] = [
    # —— 营养状态三项各自的档位 ——
    _case("healthy_young", 0, "暂无营养风险", age=30, bmi=22),
    _case("weight_loss_under_5pct", 0, "暂无营养风险",  # <5% 不凑分（回归）
          age=40, bmi=23, weight_loss_pct_3m=3, weight_loss_period_months=3),
    _case("weight_loss_6pct_3mo", 1, "暂无营养风险",
          age=40, bmi=22, weight_loss_pct_3m=6, weight_loss_period_months=3),
    _case("weight_loss_6pct_2mo", 2, "暂无营养风险",
          age=40, bmi=22, weight_loss_pct_3m=6, weight_loss_period_months=2),
    _case("weight_loss_6pct_1mo", 3, "有营养风险",
          age=40, bmi=22, weight_loss_pct_3m=6, weight_loss_period_months=1),
    _case("weight_loss_over_15pct", 3, "有营养风险",
          age=40, bmi=22, weight_loss_pct_3m=16, weight_loss_period_months=3),
    _case("intake_50_75pct", 1, "暂无营养风险", age=40, bmi=22, food_intake_drop_pct=38),
    _case("intake_25_50pct", 2, "暂无营养风险", age=40, bmi=22, food_intake_drop_pct=63),
    _case("intake_under_25pct", 3, "有营养风险", age=40, bmi=22, food_intake_drop_pct=88),
    _case("bmi_18_5_to_20_5", 2, "暂无营养风险", age=40, bmi=19.5),
    _case("bmi_under_18_5", 3, "有营养风险", age=40, bmi=17),
    # —— 年龄 / 疾病 / 组合 ——
    _case("elderly_only", 1, "暂无营养风险", age=72, bmi=22),  # ≥70 → +1
    _case("elderly_plus_intake", 2, "暂无营养风险", age=72, bmi=22, food_intake_drop_pct=38),
    _case("boundary_exactly_3", 3, "有营养风险",  # BMI 2 + 年龄 1 = 3，恰好踩线
          age=70, bmi=20, disease_severity=DiseaseSeverity.NONE),
    _case("severe_disease_only", 3, "有营养风险",
          age=50, bmi=24, disease_severity=DiseaseSeverity.SEVERE),
    _case("multi_dimension_high", 6, "有营养风险",
          age=72, bmi=17, weight_loss_pct_3m=8, weight_loss_period_months=3,
          food_intake_drop_pct=60, disease_severity=DiseaseSeverity.MODERATE),
]


def _scoring_signature(report: NRSReport) -> tuple:
    """评分签名 —— 只取确定性字段，排除非确定性的 answered_at 时间戳。"""
    return (
        report.nutrition_score,
        report.disease_score,
        report.age_score,
        report.total_score,
        report.risk_level,
    )


def _is_complete(report: NRSReport) -> bool:
    return (
        0 <= report.nutrition_score <= 3
        and 0 <= report.disease_score <= 3
        and 0 <= report.age_score <= 1
        and 0 <= report.total_score <= 7
        and report.risk_level in _VALID_LEVELS
        and bool(report.recommendation.strip())
    )


def score_accuracy(cases: list[GoldCase]) -> float:
    if not cases:
        return 0.0
    hits = 0
    for c in cases:
        r = compute_nrs2002(c.case_id, c.answer)
        if r.total_score == c.expected_total and r.risk_level == c.expected_level:
            hits += 1
    return hits / len(cases)


def report_completeness(cases: list[GoldCase]) -> float:
    if not cases:
        return 0.0
    ok = sum(_is_complete(compute_nrs2002(c.case_id, c.answer)) for c in cases)
    return ok / len(cases)


def retest_consistency(cases: list[GoldCase], runs: int = 3) -> float:
    """同一输入跑 `runs` 次评分签名是否恒一致 —— 验证确定性（应 = 1.0）。"""
    if not cases:
        return 0.0
    stable = 0
    for c in cases:
        sigs = {_scoring_signature(compute_nrs2002(c.case_id, c.answer)) for _ in range(runs)}
        if len(sigs) == 1:
            stable += 1
    return stable / len(cases)


def evaluate_screening(cases: list[GoldCase] | None = None) -> ScreeningMetric:
    cases = cases if cases is not None else GOLD_CASES
    return ScreeningMetric(
        score_accuracy=score_accuracy(cases),
        report_completeness=report_completeness(cases),
        retest_consistency=retest_consistency(cases),
    )


def main() -> None:
    import json

    from app.evaluation.metrics import aggregate_dashboard

    dashboard = aggregate_dashboard(evaluate_screening())
    print(json.dumps(dashboard, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
