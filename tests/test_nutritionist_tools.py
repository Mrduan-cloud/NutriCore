"""营养师 Function Calling 工具单测 —— 纯逻辑,无 LLM / 网络,可进 CI。

覆盖三层:
1. 纯函数内核(BMI / BMR / 能量目标)的数值与边界;
2. ``@tool`` 外壳的 LangChain 装配(name / description / args / invoke);
3. 安全不变量(能量目标永不低于 BMR)与异常兜底(脏输入返回友好提示而非抛栈)。
"""
import pytest

from app.agents.nutritionist.tools import (
    NUTRITIONIST_TOOLS,
    bmi_category,
    bmi_report,
    calculate_bmi,
    compute_bmi,
    consult_tool_context,
    daily_energy_target,
    estimate_daily_energy,
    healthy_weight_range_kg,
    mifflin_st_jeor_bmr,
    mifflin_st_jeor_bmr_raw,
)


# ---------- compute_bmi ----------
def test_compute_bmi_value_and_rounding():
    # 70kg / 1.75m^2 = 22.857... → 22.9
    assert compute_bmi(175, 70) == 22.9
    assert compute_bmi(170, 65) == 22.5


@pytest.mark.parametrize("h,w", [(0, 60), (170, 0), (-1, 60), (170, -5)])
def test_compute_bmi_rejects_non_positive(h, w):
    with pytest.raises(ValueError):
        compute_bmi(h, w)


# ---------- bmi_category (WS/T 428-2013 边界) ----------
@pytest.mark.parametrize(
    "bmi,expected",
    [
        (18.4, "偏瘦"),
        (18.5, "正常"),
        (23.9, "正常"),
        (24.0, "超重"),
        (27.9, "超重"),
        (28.0, "肥胖"),
        (35.0, "肥胖"),
    ],
)
def test_bmi_category_boundaries(bmi, expected):
    assert bmi_category(bmi) == expected


# ---------- healthy_weight_range_kg ----------
def test_healthy_weight_range():
    low, high = healthy_weight_range_kg(170)
    # 18.5 * 1.7^2 = 53.465 → 53.5 ; 23.9 * 1.7^2 = 69.071 → 69.1
    assert low == 53.5
    assert high == 69.1
    assert low < high


def test_bmi_report_shape():
    r = bmi_report(170, 65)
    assert r["bmi"] == 22.5
    assert r["category"] == "正常"
    assert isinstance(r["healthy_weight_kg"], list) and len(r["healthy_weight_kg"]) == 2


# ---------- mifflin_st_jeor_bmr (性别差异) ----------
def test_bmr_male_vs_female():
    # 男:10*70 + 6.25*175 - 5*30 + 5 = 1648.75 → 1649
    assert mifflin_st_jeor_bmr("male", 30, 175, 70) == 1649
    # 女:同身材末项 -161 → 比男少 166
    assert mifflin_st_jeor_bmr("female", 30, 175, 70) == 1483
    # 中文 "男" 也认作男性
    assert mifflin_st_jeor_bmr("男", 30, 175, 70) == 1649


@pytest.mark.parametrize("age,h,w", [(0, 175, 70), (30, 0, 70), (30, 175, 0)])
def test_bmr_rejects_non_positive(age, h, w):
    with pytest.raises(ValueError):
        mifflin_st_jeor_bmr("male", age, h, w)


# ---------- daily_energy_target ----------
def test_energy_scales_with_activity():
    base = dict(gender="male", age=30, height_cm=175, weight_kg=70)
    sed = daily_energy_target(**base, activity_level="sedentary")["target_kcal"]
    mod = daily_energy_target(**base, activity_level="moderate")["target_kcal"]
    vig = daily_energy_target(**base, activity_level="very_active")["target_kcal"]
    assert sed < mod < vig


def test_energy_scales_with_goal():
    base = dict(gender="female", age=28, height_cm=165, weight_kg=58, activity_level="moderate")
    lose = daily_energy_target(**base, goal="lose")["target_kcal"]
    keep = daily_energy_target(**base, goal="maintain")["target_kcal"]
    gain = daily_energy_target(**base, goal="gain")["target_kcal"]
    assert lose < keep < gain


def test_energy_never_below_bmr_invariant():
    """安全不变量:任何活动 / 目标组合下,目标热量都不得低于 BMR。"""
    for act in ("sedentary", "light", "moderate", "active", "very_active"):
        for goal in ("maintain", "lose", "gain"):
            r = daily_energy_target("female", 60, 150, 45, activity_level=act, goal=goal)
            assert r["target_kcal"] >= r["bmr_kcal"]


def test_energy_macros_sum_close_to_target():
    r = daily_energy_target("male", 30, 175, 70, activity_level="moderate", goal="maintain")
    m = r["macros_g"]
    kcal_from_macros = m["carb"] * 4 + m["protein"] * 4 + m["fat"] * 9
    # 四舍五入误差容忍 ±30 kcal
    assert abs(kcal_from_macros - r["target_kcal"]) <= 30


def test_energy_unknown_inputs_fall_back():
    r = daily_energy_target("male", 30, 175, 70, activity_level="飞天", goal="成仙")
    assert r["activity_level"] == "moderate"
    assert r["goal"] == "maintain"


def test_energy_chinese_aliases():
    r = daily_energy_target("男", 30, 175, 70, activity_level="久坐", goal="减脂")
    assert r["activity_level"] == "sedentary"
    assert r["goal"] == "lose"


# ---------- @tool 外壳:LangChain 装配 ----------
def test_tools_registered():
    names = {t.name for t in NUTRITIONIST_TOOLS}
    assert names == {"calculate_bmi", "estimate_daily_energy"}
    for t in NUTRITIONIST_TOOLS:
        assert t.description  # Function Calling 靠 description 选工具
        assert t.args  # 有参数 schema


def test_calculate_bmi_tool_invoke():
    out = calculate_bmi.invoke({"height_cm": 170, "weight_kg": 65})
    assert isinstance(out, str)
    assert "BMI" in out and "22.5" in out and "正常" in out


def test_estimate_daily_energy_tool_invoke():
    out = estimate_daily_energy.invoke(
        {"gender": "male", "age": 30, "height_cm": 175, "weight_kg": 70,
         "activity_level": "moderate", "goal": "maintain"}
    )
    assert isinstance(out, str)
    assert "kcal" in out and "蛋白质" in out


def test_tool_invalid_input_is_friendly_not_raised():
    # 脏输入不抛栈,返回可读提示(避免打断 LangGraph)
    assert "无法计算" in calculate_bmi.invoke({"height_cm": 0, "weight_kg": 65})
    assert "无法估算" in estimate_daily_energy.invoke(
        {"gender": "male", "age": -1, "height_cm": 175, "weight_kg": 70}
    )


# ---------- mifflin_st_jeor_bmr_raw(canonical 不取整版) ----------
def test_bmr_raw_identity_with_rounded():
    # round(raw) 必须与取整版逐位一致(raw 是唯一公式来源)
    for gender, age, h, w in [("male", 30, 175, 70), ("female", 28, 165, 58),
                              ("男", 45, 180, 85), ("female", 60, 150, 45)]:
        assert round(mifflin_st_jeor_bmr_raw(gender, age, h, w)) == \
            mifflin_st_jeor_bmr(gender, age, h, w)
    # raw 保留小数(30 岁 175cm 70kg 男:1648.75)
    assert mifflin_st_jeor_bmr_raw("male", 30, 175, 70) == pytest.approx(1648.75)


def test_meal_plan_estimator_numeric_identity():
    """meal_plan 去重后的热量估算必须与历史公式逐位一致(防 ±1 kcal 漂移)。"""
    from app.agents.meal_plan.generator import _estimate_target_kcal

    profiles = [
        {},  # 全默认:female/30/165/60
        {"gender": "male", "age": 30, "height_cm": 175, "weight_kg": 70},
        {"gender": "female", "age": 28, "height_cm": 165, "weight_kg": 58},
        {"gender": "male", "age": 51, "height_cm": 172, "weight_kg": 81.5},
    ]
    for p in profiles:
        g = (p.get("gender") or "female").lower()
        age = int(p.get("age") or 30)
        h = float(p.get("height_cm") or 165)
        w = float(p.get("weight_kg") or 60)
        legacy = round((10 * w + 6.25 * h - 5 * age + (5 if g == "male" else -161)) * 1.4)
        assert _estimate_target_kcal(p) == legacy


# ---------- consult_tool_context(确定性前置计算注入) ----------
_PROFILE = {"gender": "male", "age": 30, "height_cm": 175, "weight_kg": 70}


def test_consult_ctx_no_trigger_returns_empty():
    assert consult_tool_context("低 GI 的主食有哪些推荐?", _PROFILE) == ""
    assert consult_tool_context("帮我做营养筛查", _PROFILE) == ""


def test_consult_ctx_bmi_from_profile():
    out = consult_tool_context("我的 BMI 正常吗?", _PROFILE)
    assert "BMI 22.9" in out and "健康体重区间" in out
    assert "不要自行心算" in out


def test_consult_ctx_message_numbers_override_profile():
    # 现场报的 165cm/80kg 必须压过画像里的 175/70
    out = consult_tool_context("我165cm 80kg,算不算胖?", _PROFILE)
    assert "BMI 29.4" in out and "肥胖" in out


def test_consult_ctx_energy_full_fields():
    out = consult_tool_context("我减脂期每天吃多少热量合适?", _PROFILE)
    assert "每日能量目标" in out and "减脂" in out and "BMR" in out


def test_consult_ctx_energy_missing_gender_degrades_to_bmi_only():
    p = {"height_cm": 165, "weight_kg": 60}  # 无 gender/age → 能量段出不来
    out = consult_tool_context("我每天需要多少卡路里?", p)
    assert "BMI" in out and "每日能量目标" not in out


def test_consult_ctx_no_fields_returns_empty():
    assert consult_tool_context("我的 BMI 是多少?", {}) == ""
    assert consult_tool_context("我的 BMI 是多少?", None) == ""
