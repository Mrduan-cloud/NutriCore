"""NRS2002 评分链路：疾病严重程度 + 营养状态 + 年龄三维评分。

参考：Kondrup J, et al. ESPEN Guidelines for Nutrition Screening 2002. Clinical Nutrition 2003.
"""
from __future__ import annotations

from datetime import datetime

from app.agents.risk_screening.schemas import NRSAnswer, NRSReport


def _weight_loss_score(pct: float, months: int) -> int:
    """体重下降 → 0-3。严格按 NRS-2002 时间窗阈值,**未达 5% = 0,不凑分**。

    - >5%/1 个月(≈ >15%/3 个月)→ 3(重度)
    - >5%/2 个月 → 2(中度)
    - >5%/3 个月 → 1(轻度)
    - ≤5% → 0
    """
    if pct > 15:
        return 3
    if pct <= 5:
        return 0
    if months <= 1:
        return 3
    if months <= 2:
        return 2
    return 1


def _intake_score(drop_pct: float) -> int:
    """近一周进食量下降 → 0-3(下降 = 占平时需要量的缺口)。

    进食为平时的 50-75%(下降 25-50%)→1;25-50%(下降 50-75%)→2;0-25%(下降≥75%)→3。
    """
    if drop_pct >= 75:
        return 3
    if drop_pct >= 50:
        return 2
    if drop_pct >= 25:
        return 1
    return 0


def _bmi_score(bmi: float) -> int:
    """BMI → 0-3(筛查口径:以 BMI 区间作为「营养状态受损」的保守代理)。

    标准 NRS-2002 在 BMI<18.5 / 18.5-20.5 时还需「一般情况受损」;本筛查从简,
    单以 BMI 区间计分,偏保守(宁可提示、不漏筛)。
    """
    if bmi < 18.5:
        return 3
    if bmi <= 20.5:
        return 2
    return 0


def nutrition_breakdown(answer: NRSAnswer) -> dict[str, int]:
    """营养状态三项子分明细(供展示);最终营养状态分 = 三者取最高。"""
    return {
        "weight_loss": _weight_loss_score(
            answer.weight_loss_pct_3m, answer.weight_loss_period_months
        ),
        "intake": _intake_score(answer.food_intake_drop_pct),
        "bmi": _bmi_score(answer.bmi),
    }


def _nutrition_score(answer: NRSAnswer) -> int:
    """营养状态评分(0-3)= 体重下降 / 进食下降 / BMI 三项取最高(NRS-2002 口径)。"""
    return max(nutrition_breakdown(answer).values())


def _age_score(age: int) -> int:
    """年龄 ≥ 70 加 1 分。"""
    return 1 if age >= 70 else 0


def _risk_level(total: int) -> tuple[str, str]:
    """NRS-2002 严格二分法(ESPEN 2002 / Kondrup),不存在"轻/中度风险"中间档。

    - 总分 ≥ 3 → **有营养风险**(at-risk):应启动个性化营养支持方案
    - 总分 < 3 → **暂无营养风险**(not at-risk):标准做法是 1 周后重新筛查

    注:1-2 分**不是**"轻度风险"——这是临床筛查工具的常见误读。
    """
    if total >= 3:
        return (
            "有营养风险",
            "应启动个性化营养支持方案,建议由专科营养师或临床医生进一步评估。",
        )
    return (
        "暂无营养风险",
        "按 NRS-2002 标准 1 周后再筛查;期间持续监测体重与进食量变化。",
    )


def compute_nrs2002(user_id: str, answer: NRSAnswer) -> NRSReport:
    """主入口：返回结构化 NRSReport。"""
    nutrition = _nutrition_score(answer)
    age = _age_score(answer.age)
    disease = int(answer.disease_severity)
    total = nutrition + disease + age
    level, recommendation = _risk_level(total)
    return NRSReport(
        user_id=user_id,
        nutrition_score=nutrition,
        disease_score=disease,
        age_score=age,
        total_score=total,
        risk_level=level,
        recommendation=recommendation,
        answered_at=datetime.utcnow().isoformat(),
    )
