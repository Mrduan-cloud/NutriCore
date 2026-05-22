"""NRS2002 评分单测样例。"""
from app.agents.risk_screening.schemas import NRSAnswer, DiseaseSeverity
from app.agents.risk_screening.nrs2002 import compute_nrs2002


def test_low_risk():
    ans = NRSAnswer(age=30, bmi=22, weight_loss_pct_3m=0, food_intake_drop_pct=0)
    r = compute_nrs2002("u1", ans)
    assert r.total_score == 0
    assert r.risk_level == "无风险"


def test_high_risk_elderly():
    ans = NRSAnswer(
        age=72, bmi=17, weight_loss_pct_3m=8, food_intake_drop_pct=60,
        disease_severity=DiseaseSeverity.MODERATE,
    )
    r = compute_nrs2002("u2", ans)
    assert r.total_score >= 3
    assert r.risk_level == "建议营养支持"
