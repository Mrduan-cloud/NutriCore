"""NRS2002 评分链路：疾病严重程度 + 营养状态 + 年龄三维评分。

参考：Kondrup J, et al. ESPEN Guidelines for Nutrition Screening 2002. Clinical Nutrition 2003.
"""
from __future__ import annotations

from datetime import datetime
from app.agents.risk_screening.schemas import NRSAnswer, NRSReport


def _nutrition_score(answer: NRSAnswer) -> int:
    """根据 BMI / 体重下降 / 进食量下降，输出营养状态评分（0–3）。"""
    if answer.bmi < 18.5 and answer.food_intake_drop_pct > 0:
        return 3
    if answer.weight_loss_pct_3m > 5 or answer.food_intake_drop_pct >= 50:
        return 2
    if answer.weight_loss_pct_3m > 0 or answer.food_intake_drop_pct >= 25:
        return 1
    return 0


def _age_score(age: int) -> int:
    """年龄 ≥ 70 加 1 分。"""
    return 1 if age >= 70 else 0


def _risk_level(total: int) -> tuple[str, str]:
    if total >= 3:
        return "建议营养支持", "建议尽快制定个性化营养方案，并考虑专科医生介入。"
    if total >= 1:
        return "存在风险", "建议持续监测体重与进食情况，可启用 7 天营养方案干预。"
    return "无风险", "继续保持当前膳食结构，定期复测即可。"


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
