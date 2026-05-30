"""NRS2002 结构化字段定义 — Pydantic + JSONSchema 双层校验。"""
from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, Field, field_validator


class DiseaseSeverity(IntEnum):
    """疾病严重程度评分（0–3 分）。"""

    NONE = 0
    MILD = 1            # 髋骨折 / 慢病急性发作 / 一般肿瘤 / 血透
    MODERATE = 2        # 腹部大手术 / 中风 / 重度肺炎 / 血液系统肿瘤
    SEVERE = 3          # 颅脑损伤 / 骨髓移植 / APACHE > 10 的 ICU 患者


class NutritionStatus(IntEnum):
    """营养状态评分（0–3 分）。"""

    NORMAL = 0
    MILD = 1
    MODERATE = 2
    SEVERE = 3


class NRSAnswer(BaseModel):
    """用户答题输入（结构化采集）。"""

    age: int = Field(..., ge=0, le=120)
    bmi: float = Field(..., ge=10, le=60)
    weight_loss_pct_3m: float = Field(
        0, ge=0, le=100, description="体重下降百分比(按 weight_loss_period_months 给定的时间窗)"
    )
    weight_loss_period_months: int = Field(
        3, ge=1, le=3, description="体重下降发生的时间窗(月):1/2/3,用于套用 NRS-2002 不同阈值"
    )
    food_intake_drop_pct: float = Field(0, ge=0, le=100, description="近 1 周进食量下降百分比")
    disease_severity: DiseaseSeverity = DiseaseSeverity.NONE

    @field_validator("bmi")
    @classmethod
    def warn_extreme_bmi(cls, v: float) -> float:
        if v < 13 or v > 50:
            raise ValueError("BMI 超出可接受范围，可能录入错误")
        return v


class NRSReport(BaseModel):
    """NRS2002 评分结果（用于生成 PDF 报告）。"""

    user_id: str
    nutrition_score: int = Field(..., ge=0, le=3)
    disease_score: int = Field(..., ge=0, le=3)
    age_score: int = Field(..., ge=0, le=1)
    total_score: int = Field(..., ge=0, le=7)
    risk_level: str            # "无风险" / "存在风险" / "建议营养支持"
    recommendation: str
    answered_at: str
