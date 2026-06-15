"""Eval 看板统一入口测试 —— 三维汇总结构 + gold 基线值 + live 路径注入/回落。"""
from app.evaluation import dashboard as dash_mod
from app.evaluation.dashboard import run_dashboard, run_dashboard_live
from app.evaluation.insight_eval import GOLD_SQL_GEN_CASES, replay_generator
from app.evaluation.plan_eval import LIVE_RECALL_GOLD


def test_dashboard_has_all_three_dimensions():
    assert set(run_dashboard()) == {"ScreeningMetric", "PlanMetric", "InsightMetric"}


def test_dashboard_metric_fields():
    dash = run_dashboard()
    assert set(dash["ScreeningMetric"]) == {
        "score_accuracy", "report_completeness", "retest_consistency",
    }
    assert set(dash["PlanMetric"]) == {"recall_at_k", "citation_hit_rate", "compliance_rate"}
    assert set(dash["InsightMetric"]) == {
        "sql_accuracy", "chart_success_rate", "interpretation_readability", "e2e_sql_accuracy",
    }


def test_dashboard_gold_baseline_values():
    """gold 基线：确定性维度应满分；离线 recall 记 0.0（需 W09 真实检索）。"""
    dash = run_dashboard()
    s, p, i = dash["ScreeningMetric"], dash["PlanMetric"], dash["InsightMetric"]
    assert (s["score_accuracy"], s["report_completeness"], s["retest_consistency"]) == (1.0, 1.0, 1.0)
    assert (p["compliance_rate"], p["citation_hit_rate"]) == (1.0, 1.0)
    assert p["recall_at_k"] == 0.0  # 离线不评，--live 才接真实检索
    assert (i["sql_accuracy"], i["chart_success_rate"], i["interpretation_readability"]) == (1.0, 1.0, 1.0)
    assert i["e2e_sql_accuracy"] == 0.0  # 离线不评端到端生成，--live 才接真实 LLM


# —— live 看板路径（CI 安全：monkeypatch 桩，不连网/库）——


def test_dashboard_live_falls_back_when_unavailable(monkeypatch):
    """真实检索 / 生成不可用（构造即抛）→ 各维度回落离线值，不崩。"""
    def boom():
        raise RuntimeError("stack down")

    monkeypatch.setattr(dash_mod, "_live_recall_retriever", boom)
    monkeypatch.setattr(dash_mod, "_live_sql_generator", boom)
    dash = run_dashboard_live()
    assert set(dash) == {"ScreeningMetric", "PlanMetric", "InsightMetric"}
    assert dash["PlanMetric"]["recall_at_k"] == 0.0       # 回落
    assert dash["InsightMetric"]["e2e_sql_accuracy"] == 0.0  # 回落
    assert dash["InsightMetric"]["sql_accuracy"] == 1.0   # 离线维度照常


def test_dashboard_live_uses_injected_real_components(monkeypatch):
    """注入「真组件」桩：retriever 命中 gold、generator 回放 ideal_sql → 看板显示真值。"""
    relevant = {q: docs for q, docs in LIVE_RECALL_GOLD}

    def fake_retriever_factory():
        return lambda query: list(relevant.get(query, set()))  # 命中相关文档 → recall 1.0

    def fake_generator_factory():
        return replay_generator(GOLD_SQL_GEN_CASES)  # 回放 ideal_sql → e2e 1.0

    monkeypatch.setattr(dash_mod, "_live_recall_retriever", fake_retriever_factory)
    monkeypatch.setattr(dash_mod, "_live_sql_generator", fake_generator_factory)
    dash = run_dashboard_live()
    assert dash["PlanMetric"]["recall_at_k"] == 1.0
    assert dash["InsightMetric"]["e2e_sql_accuracy"] == 1.0
