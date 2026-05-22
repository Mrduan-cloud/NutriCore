"""食物营养查询工具。"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class FoodNutritionInput(BaseModel):
    food_name: str = Field(..., min_length=1)
    portion_g: float = Field(100, gt=0)


def _query_food_nutrition(food_name: str, portion_g: float) -> dict:
    # TODO: 查询食材成分库（MySQL / Milvus 同义词）
    return {
        "food": food_name,
        "portion_g": portion_g,
        "kcal": 0,
        "protein_g": 0,
        "fat_g": 0,
        "carb_g": 0,
    }


food_nutrition_tool = StructuredTool.from_function(
    func=_query_food_nutrition,
    name="food_nutrition",
    description="查询食物的营养成分（每份克数下的热量与三大宏量）。",
    args_schema=FoodNutritionInput,
)
