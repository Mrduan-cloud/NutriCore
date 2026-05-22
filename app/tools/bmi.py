"""BMI 计算工具。"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class BMIInput(BaseModel):
    height_cm: float = Field(..., gt=50, lt=250)
    weight_kg: float = Field(..., gt=10, lt=300)


def _compute_bmi(height_cm: float, weight_kg: float) -> dict:
    h = height_cm / 100
    bmi = round(weight_kg / (h * h), 2)
    if bmi < 18.5:
        cat = "偏瘦"
    elif bmi < 24:
        cat = "正常"
    elif bmi < 28:
        cat = "超重"
    else:
        cat = "肥胖"
    return {"bmi": bmi, "category": cat}


bmi_tool = StructuredTool.from_function(
    func=_compute_bmi,
    name="bmi_calc",
    description="根据身高 (cm) 和体重 (kg) 计算 BMI 并给出中文分类。",
    args_schema=BMIInput,
)
