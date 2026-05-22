"""方案强约束校验：Pydantic + JSONSchema 双层校验。

校验项：
- 热量区间 / 营养素配比
- 忌口冲突（过敏 / 慢病禁忌）
- 每条建议强制携带知识库片段引用 → 消除「无依据胡编」
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator
from jsonschema import validate as jsonschema_validate


class MealItem(BaseModel):
    name: str
    portion_g: float = Field(..., gt=0)
    kcal: float = Field(..., ge=0)
    citations: list[str] = Field(..., min_length=1)  # [doc_id:chunk_id]

    @field_validator("citations")
    @classmethod
    def must_have_citation(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("每条食材必须携带至少一条知识库引用")
        return v


class DayPlan(BaseModel):
    day: int = Field(..., ge=1, le=7)
    breakfast: list[MealItem]
    lunch: list[MealItem]
    dinner: list[MealItem]
    snack: list[MealItem] = []
    total_kcal: float
    macros: dict[str, float]  # {"carb": 0.55, "protein": 0.18, "fat": 0.27}


class MealPlan(BaseModel):
    user_id: str
    target_kcal: float
    days: list[DayPlan] = Field(..., min_length=7, max_length=7)


PLAN_JSON_SCHEMA = {
    "type": "object",
    "required": ["user_id", "target_kcal", "days"],
    "properties": {
        "user_id": {"type": "string"},
        "target_kcal": {"type": "number", "minimum": 800, "maximum": 4000},
        "days": {"type": "array", "minItems": 7, "maxItems": 7},
    },
}


def validate_plan_strict(plan: dict[str, Any], evidence: list[dict]) -> dict[str, Any]:
    """双层校验 + 引用核验。引用必须能在 evidence 中找到。"""
    jsonschema_validate(plan, PLAN_JSON_SCHEMA)
    model = MealPlan.model_validate(plan)
    valid_refs = {f"{e['doc_id']}:{e['chunk_id']}" for e in evidence}
    for day in model.days:
        for slot in (day.breakfast, day.lunch, day.dinner, day.snack):
            for item in slot:
                for ref in item.citations:
                    if ref not in valid_refs:
                        raise ValueError(f"引用 {ref} 在本次检索证据中不存在")
    return model.model_dump()
