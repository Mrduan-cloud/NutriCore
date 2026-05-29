"""NRS2002 确定性评分单测。"""
from app.agents.risk_screening.nrs2002 import compute_nrs2002, nutrition_breakdown
from app.agents.risk_screening.schemas import DiseaseSeverity, NRSAnswer


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


def test_small_weight_loss_is_zero():
    """关键回归:<5% 的体重下降不该凑分,营养状态 = 0(此前误判为 1)。"""
    ans = NRSAnswer(age=32, bmi=25.5, weight_loss_pct_3m=2.0, weight_loss_period_months=3,
                    food_intake_drop_pct=0)
    r = compute_nrs2002("u", ans)
    assert nutrition_breakdown(ans)["weight_loss"] == 0
    assert r.nutrition_score == 0
    assert r.total_score == 0


def test_weight_loss_thresholds_by_period():
    """同样 >5% 的下降,时间窗越短分越高(3mo→1, 2mo→2, 1mo→3)。"""
    def wl(months):
        a = NRSAnswer(age=40, bmi=22, weight_loss_pct_3m=6, weight_loss_period_months=months)
        return nutrition_breakdown(a)["weight_loss"]

    assert wl(3) == 1
    assert wl(2) == 2
    assert wl(1) == 3


def test_weight_loss_over_15pct_is_severe():
    a = NRSAnswer(age=40, bmi=22, weight_loss_pct_3m=16, weight_loss_period_months=3)
    assert nutrition_breakdown(a)["weight_loss"] == 3


def test_intake_bands():
    def intake(drop):
        a = NRSAnswer(age=40, bmi=22, food_intake_drop_pct=drop)
        return nutrition_breakdown(a)["intake"]

    assert intake(10) == 0   # 进食 >75%
    assert intake(38) == 1   # 进食 50-75%
    assert intake(63) == 2   # 进食 25-50%
    assert intake(88) == 3   # 进食 0-25%


def test_bmi_bands():
    def bmi_score(bmi):
        a = NRSAnswer(age=40, bmi=bmi)
        return nutrition_breakdown(a)["bmi"]

    assert bmi_score(25) == 0
    assert bmi_score(19.5) == 2
    assert bmi_score(17) == 3


def test_nutrition_takes_max_dimension():
    """营养状态 = 体重/进食/BMI 三项取最高。"""
    ans = NRSAnswer(age=40, bmi=22, weight_loss_pct_3m=6, weight_loss_period_months=3,
                    food_intake_drop_pct=88)  # weight=1, intake=3, bmi=0
    assert compute_nrs2002("u", ans).nutrition_score == 3


def test_age_adds_one_at_70():
    young = NRSAnswer(age=69, bmi=22)
    old = NRSAnswer(age=70, bmi=22)
    assert compute_nrs2002("u", young).age_score == 0
    assert compute_nrs2002("u", old).age_score == 1
