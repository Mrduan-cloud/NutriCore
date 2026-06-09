"""营养师 Function Calling 工具 —— BMI 与每日能量目标。

把原先散落在 ``memory`` / ``meal_plan`` / ``risk_screening`` 里的确定性算法,
收敛成可被 LLM **Function Calling** 直接调用的工具。设计要点:

- **纯函数内核 + ``@tool`` 外壳**:所有计算在纯函数里完成(确定性、可单测、
  可进 CI,不依赖 LLM / 网络);``@tool`` 外壳只做参数归一化、异常兜底、结果排版。
- **安全边界**:每日能量目标永不低于基础代谢率 BMR —— 长期低于 BMR 进食有害,
  即便用户目标是激进减脂也兜底到 BMR;极端 / 缺失输入由外壳兜底为友好提示,
  绝不让异常冒泡打断 LangGraph。
- **不替代诊疗**:工具只做营养常识范畴的换算,涉及疾病 / 用药仍由上层
  ``safety_fallback`` 拦截。

绑定示例(后续节点接入 tool-calling 时)::

    from app.agents.nutritionist.tools import NUTRITIONIST_TOOLS
    llm_with_tools = llm.bind_tools(NUTRITIONIST_TOOLS)
"""
from __future__ import annotations

from langchain_core.tools import tool

# ============ 常量 ============
# Mifflin-St Jeor PAL(体力活动水平)系数 —— 营养学主流取值
_ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,     # 久坐,几乎不运动
    "light": 1.375,       # 轻度,每周 1-3 次轻运动
    "moderate": 1.55,     # 中度,每周 3-5 次
    "active": 1.725,      # 高度,每周 6-7 次
    "very_active": 1.9,   # 极高,体力劳动 / 每天高强度训练
}
# 中文别名 → 标准枚举(LLM 偶尔会直接传中文)
_ACTIVITY_ALIASES: dict[str, str] = {
    "久坐": "sedentary", "不运动": "sedentary",
    "轻度": "light", "轻": "light", "偶尔": "light",
    "中度": "moderate", "中": "moderate", "适中": "moderate",
    "高度": "active", "活跃": "active", "经常": "active",
    "极高": "very_active", "重体力": "very_active",
}
# 目标对 TDEE 的调整(减脂 -15% / 维持 / 增肌 +15%)
_GOAL_FACTORS: dict[str, float] = {"maintain": 1.0, "lose": 0.85, "gain": 1.15}
_GOAL_ALIASES: dict[str, str] = {
    "维持": "maintain", "保持": "maintain",
    "减脂": "lose", "减重": "lose", "减肥": "lose", "瘦": "lose",
    "增肌": "gain", "增重": "gain", "长肉": "gain",
}
_GOAL_CN = {"maintain": "维持", "lose": "减脂", "gain": "增肌"}

# WS/T 428-2013「正常」区间(<24 为上界,取闭区间近似 23.9)
_BMI_NORMAL_LOW = 18.5
_BMI_NORMAL_HIGH = 23.9


# ============ 纯函数内核(可单测 / 进 CI) ============
def compute_bmi(height_cm: float, weight_kg: float) -> float:
    """BMI = 体重(kg) / 身高(m)²,保留 1 位小数。身高、体重必须为正。"""
    h_cm, w = float(height_cm), float(weight_kg)
    if h_cm <= 0 or w <= 0:
        raise ValueError("身高、体重必须为正数")
    h = h_cm / 100.0
    return round(w / (h * h), 1)


def bmi_category(bmi: float) -> str:
    """中国成人 BMI 分级(WS/T 428-2013):偏瘦 / 正常 / 超重 / 肥胖。"""
    if bmi < 18.5:
        return "偏瘦"
    if bmi < 24:
        return "正常"
    if bmi < 28:
        return "超重"
    return "肥胖"


def healthy_weight_range_kg(height_cm: float) -> tuple[float, float]:
    """给定身高,返回 BMI 正常区间(18.5–23.9)对应的体重范围(kg)。"""
    h_cm = float(height_cm)
    if h_cm <= 0:
        raise ValueError("身高必须为正数")
    h = h_cm / 100.0
    return (round(_BMI_NORMAL_LOW * h * h, 1), round(_BMI_NORMAL_HIGH * h * h, 1))


def bmi_report(height_cm: float, weight_kg: float) -> dict:
    """BMI 一站式结果:数值 + 分级 + 健康体重区间。"""
    bmi = compute_bmi(height_cm, weight_kg)
    low, high = healthy_weight_range_kg(height_cm)
    return {"bmi": bmi, "category": bmi_category(bmi), "healthy_weight_kg": [low, high]}


def mifflin_st_jeor_bmr(gender: str, age: int, height_cm: float, weight_kg: float) -> int:
    """基础代谢率 BMR(Mifflin-St Jeor)。

    男:10·w + 6.25·h − 5·age + 5;女:同式末项 −161。年龄/身高/体重须为正。
    """
    a, h, w = int(age), float(height_cm), float(weight_kg)
    if a <= 0 or h <= 0 or w <= 0:
        raise ValueError("年龄、身高、体重必须为正数")
    sex_const = 5 if str(gender).strip().lower() in ("male", "m", "男") else -161
    return round(10 * w + 6.25 * h - 5 * a + sex_const)


def _macro_grams(kcal: float) -> dict[str, int]:
    """按碳水 50% / 蛋白质 20% / 脂肪 30% 折算克数(4 / 4 / 9 kcal·g⁻¹)。"""
    return {
        "carb": round(kcal * 0.50 / 4),
        "protein": round(kcal * 0.20 / 4),
        "fat": round(kcal * 0.30 / 9),
    }


def daily_energy_target(
    gender: str,
    age: int,
    height_cm: float,
    weight_kg: float,
    activity_level: str = "moderate",
    goal: str = "maintain",
) -> dict:
    """每日能量目标:BMR → TDEE(×活动系数)→ 目标(×目标系数,下限 BMR)。

    返回 ``{bmr_kcal, tdee_kcal, activity_level, goal, target_kcal, macros_g}``。
    未识别的 activity_level / goal 回退到 moderate / maintain。
    """
    bmr = mifflin_st_jeor_bmr(gender, age, height_cm, weight_kg)

    act = _ACTIVITY_ALIASES.get(str(activity_level).strip(), str(activity_level).strip().lower())
    if act not in _ACTIVITY_FACTORS:
        act = "moderate"
    g = _GOAL_ALIASES.get(str(goal).strip(), str(goal).strip().lower())
    if g not in _GOAL_FACTORS:
        g = "maintain"

    tdee = bmr * _ACTIVITY_FACTORS[act]
    # 安全下限:目标热量不低于 BMR(长期低于基础代谢进食有害)
    target = max(round(tdee * _GOAL_FACTORS[g]), bmr)
    return {
        "bmr_kcal": bmr,
        "tdee_kcal": round(tdee),
        "activity_level": act,
        "goal": g,
        "target_kcal": target,
        "macros_g": _macro_grams(target),
    }


# ============ @tool 外壳(LLM Function Calling 入口) ============
@tool
def calculate_bmi(height_cm: float, weight_kg: float) -> str:
    """计算 BMI(体质指数)并给出中国成人分级与健康体重区间。

    适用:用户给了身高(cm)和体重(kg),想知道胖瘦 / 是否标准。
    参数:height_cm 身高(厘米,如 170)、weight_kg 体重(千克,如 65)。
    返回 BMI 数值、分级(偏瘦 / 正常 / 超重 / 肥胖)与该身高的健康体重范围。
    """
    try:
        r = bmi_report(height_cm, weight_kg)
    except (ValueError, TypeError):
        return "无法计算 BMI:请提供有效的身高(cm)和体重(kg)。"
    low, high = r["healthy_weight_kg"]
    return (
        f"BMI {r['bmi']}({r['category']})。"
        f"该身高的健康体重区间约 {low}–{high} kg。"
    )


@tool
def estimate_daily_energy(
    gender: str,
    age: int,
    height_cm: float,
    weight_kg: float,
    activity_level: str = "moderate",
    goal: str = "maintain",
) -> str:
    """估算每日能量目标(kcal)与三大营养素克数,基于 Mifflin-St Jeor 公式。

    适用:用户想知道每天该摄入多少热量 / 减脂或增肌的热量目标。
    参数:
    - gender 性别:male / female(也认 男 / 女)
    - age 年龄(岁)、height_cm 身高(厘米)、weight_kg 体重(千克)
    - activity_level 体力活动:sedentary / light / moderate / active / very_active,默认 moderate
    - goal 目标:maintain(维持) / lose(减脂) / gain(增肌),默认 maintain
    返回 BMR、TDEE、目标热量(已兜底不低于 BMR)与碳水 / 蛋白质 / 脂肪克数。
    """
    try:
        r = daily_energy_target(gender, age, height_cm, weight_kg, activity_level, goal)
    except (ValueError, TypeError):
        return "无法估算每日能量:请提供有效的性别、年龄、身高(cm)、体重(kg)。"
    m = r["macros_g"]
    return (
        f"每日能量目标约 {r['target_kcal']} kcal({_GOAL_CN[r['goal']]})。"
        f"基础代谢 BMR {r['bmr_kcal']} kcal、活动消耗 TDEE {r['tdee_kcal']} kcal。"
        f"建议三大营养素:碳水 {m['carb']}g、蛋白质 {m['protein']}g、脂肪 {m['fat']}g。"
    )


# 供后续 ``llm.bind_tools(NUTRITIONIST_TOOLS)`` 一次性绑定
NUTRITIONIST_TOOLS = [calculate_bmi, estimate_daily_energy]

__all__ = [
    "NUTRITIONIST_TOOLS",
    "bmi_category",
    "bmi_report",
    "calculate_bmi",
    "compute_bmi",
    "daily_energy_target",
    "estimate_daily_energy",
    "healthy_weight_range_kg",
    "mifflin_st_jeor_bmr",
]
