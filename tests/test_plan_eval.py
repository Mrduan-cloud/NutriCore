"""方案评测器单测 —— 守住 compliance / citation_hit / recall@k 三个指标的正确性。

要点：
- 内置样例方案合规且引用齐全 → compliance / citation 应 = 1.0。
- 但指标要**能区分**：破坏结构 → compliance 掉；引用部分越界 → citation_hit 给部分 credit（而非像二元校验直接 0/1）。
- recall@k 是注入式纯函数：用确定性 stub retriever 验证 top-k 截断与命中计算。
"""
from app.evaluation.metrics import aggregate_dashboard
from app.evaluation.plan_eval import (
    GOLD_PLAN_CASES,
    PlanCase,
    citation_hit_rate,
    compliance_rate,
    evaluate_plan,
    recall_at_k,
)


def test_gold_plans_full_compliance():
    assert compliance_rate(GOLD_PLAN_CASES) == 1.0


def test_gold_plans_full_citation_hit():
    assert citation_hit_rate(GOLD_PLAN_CASES) == 1.0


def test_compliance_detects_broken_plan():
    """**关键**：结构破坏（只剩 6 天）必须把合规率拉低，证明指标不是恒 1.0。"""
    broken = GOLD_PLAN_CASES[0].plan.copy()
    broken["days"] = broken["days"][:6]  # 违反 7 天约束
    cases = [PlanCase(broken, GOLD_PLAN_CASES[0].evidence)]
    assert compliance_rate(cases) == 0.0


def test_citation_hit_gives_partial_credit():
    """引用部分越界：二元校验会整份 fail，但 citation_hit_rate 给部分分。"""
    plan = {
        "user_id": "u", "target_kcal": 1800,
        "days": [{
            "day": 1,
            "breakfast": [{"name": "a", "portion_g": 50, "kcal": 100,
                           "citations": ["dietary_guide_2022_excerpt:0", "ghost:9"]}],
            "lunch": [], "dinner": [], "snack": [],
            "total_kcal": 1800, "macros": {"carb": 0.5, "protein": 0.2, "fat": 0.3},
        }],
    }
    evidence = [{"doc_id": "dietary_guide_2022_excerpt", "chunk_id": "0", "text": "."}]
    # 2 条引用，命中 1 条 → 0.5
    assert citation_hit_rate([PlanCase(plan, evidence)]) == 0.5
    # 而二元校验直接判不合规
    assert compliance_rate([PlanCase(plan, evidence)]) == 0.0


def test_recall_at_k_respects_cutoff():
    """top-k 截断要生效：相关文档排在 k 之外则不计入。"""
    gold = [("早餐优质蛋白", {"A", "B"})]

    def retr(_q):
        return ["A", "X", "Y", "B", "Z"]  # B 排在第 4 位

    assert recall_at_k(gold, retr, k=2) == 0.5   # top-2 只命中 A → 1/2
    assert recall_at_k(gold, retr, k=5) == 1.0    # top-5 命中 A、B → 2/2


def test_recall_at_k_zero_when_nothing_relevant():
    assert recall_at_k([("q", {"A"})], lambda _q: ["X", "Y"], k=5) == 0.0


def test_recall_at_k_empty_gold():
    assert recall_at_k([], lambda _q: ["A"], k=5) == 0.0


def test_evaluate_plan_offline_skips_recall():
    """不传 retriever → recall 记 0.0；compliance / citation 仍离线算出。"""
    m = evaluate_plan(GOLD_PLAN_CASES)
    assert m.recall_at_k == 0.0
    assert m.compliance_rate == 1.0
    assert m.citation_hit_rate == 1.0


def test_evaluate_plan_with_injected_retriever():
    gold = [("q", {"A", "B"})]
    m = evaluate_plan(GOLD_PLAN_CASES, recall_gold=gold, retriever=lambda _q: ["A", "B"], k=5)
    assert m.recall_at_k == 1.0


def test_empty_cases_zero_not_crash():
    assert compliance_rate([]) == 0.0
    assert citation_hit_rate([]) == 0.0


def test_dashboard_aggregation_shape():
    dash = aggregate_dashboard(evaluate_plan(GOLD_PLAN_CASES))
    assert set(dash["PlanMetric"]) == {"recall_at_k", "citation_hit_rate", "compliance_rate"}
