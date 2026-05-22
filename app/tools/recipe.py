"""食谱生成工具（轻量版） — 给定食材清单和热量目标，生成单餐食谱。"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class RecipeInput(BaseModel):
    target_kcal: float = Field(..., gt=100, lt=2000)
    preferred_ingredients: list[str] = Field(default_factory=list)
    avoid_ingredients: list[str] = Field(default_factory=list)


def _gen_recipe(target_kcal: float, preferred_ingredients: list[str], avoid_ingredients: list[str]) -> dict:
    # TODO: 真实实现接 LLM + 食材成分库
    return {
        "name": "示例食谱",
        "kcal": target_kcal,
        "ingredients": preferred_ingredients or ["燕麦", "鸡胸肉", "西兰花"],
        "steps": ["步骤占位"],
    }


recipe_gen_tool = StructuredTool.from_function(
    func=_gen_recipe,
    name="recipe_gen",
    description="给定热量目标 / 偏好 / 禁忌，生成单餐食谱。",
    args_schema=RecipeInput,
)
