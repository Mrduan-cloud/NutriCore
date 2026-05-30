"""Function Calling 工具集 — 基于 LangChain StructuredTool 封装。

统一规范：参数校验（Pydantic）+ 超时熔断（tenacity）+ 审计日志。
"""
from langchain_core.tools import StructuredTool

from app.tools.bmi import bmi_tool
from app.tools.disease_taboo import disease_taboo_tool
from app.tools.energy import energy_target_tool
from app.tools.food_nutrition import food_nutrition_tool
from app.tools.recipe import recipe_gen_tool

ALL_TOOLS: list[StructuredTool] = [
    bmi_tool,
    energy_target_tool,
    recipe_gen_tool,
    food_nutrition_tool,
    disease_taboo_tool,
]
