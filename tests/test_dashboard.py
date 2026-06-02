"""Eval 看板统一入口测试 —— 三维汇总结构 + gold 基线值。"""
from app.evaluation.dashboard import run_dashboard


def test_dashboard_has_all_three_dimensions():
    assert set(run_dashboard()) == {"ScreeningMetric", "PlanMetric", "InsightMetric"}


def test_dashboard_metric_fields():
    dash = run_dashboard()
    assert set(dash["ScreeningMetric"]) == {
        "score_accuracy", "report_completeness", "retest_consistency",
    }
    assert set(dash["PlanMetric"]) == {"recall_at_k", "citation_hit_rate", "compliance_rate"}
    assert set(dash["InsightMetric"]) == {
        "sql_accuracy", "chart_success_rate", "interpretation_readability",
    }


def test_dashboard_gold_baseline_values():
    """gold 基线：确定性维度应满分；离线 recall 记 0.0（需 W09 真实检索）。"""
    dash = run_dashboard()
    s, p, i = dash["ScreeningMetric"], dash["PlanMetric"], dash["InsightMetric"]
    assert (s["score_accuracy"], s["report_completeness"], s["retest_consistency"]) == (1.0, 1.0, 1.0)
    assert (p["compliance_rate"], p["citation_hit_rate"]) == (1.0, 1.0)
    assert p["recall_at_k"] == 0.0  # 离线不评，留 W09 接真实检索
    assert (i["sql_accuracy"], i["chart_success_rate"], i["interpretation_readability"]) == (1.0, 1.0, 1.0)
