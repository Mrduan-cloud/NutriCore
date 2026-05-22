"""每日能量目标 — Mifflin-St Jeor 公式 + 活动系数。"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class EnergyInput(BaseModel):
    gender: str = Field(..., pattern="^(male|female)$")
    age: int = Field(..., ge=10, le=100)
    height_cm: float = Field(..., gt=50, lt=250)
    weight_kg: float = Field(..., gt=10, lt=300)
    activity_level: float = Field(1.4, ge=1.2, le=2.0, description="1.2 久坐 ~ 1.9 重体力")


def _energy_target(gender: str, age: int, height_cm: float, weight_kg: float, activity_level: float) -> dict:
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if gender == "male" else -161)
    tdee = round(bmr * activity_level)
    return {"bmr_kcal": round(bmr), "tdee_kcal": tdee}


energy_target_tool = StructuredTool.from_function(
    func=_energy_target,
    name="energy_target",
    description="根据画像计算基础代谢 (BMR) 与每日总能量消耗 (TDEE)。",
    args_schema=EnergyInput,
)
