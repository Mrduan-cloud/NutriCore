"""慢病饮食禁忌查询工具。"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class DiseaseTabooInput(BaseModel):
    disease: str = Field(..., min_length=1, description="如：高血压 / 糖尿病 / 痛风")


_TABOO_TABLE = {
    "高血压": ["腌制食品", "高钠调料", "动物内脏"],
    "糖尿病": ["精制糖", "含糖饮料", "高 GI 主食"],
    "痛风": ["啤酒", "动物内脏", "海鲜（高嘌呤）"],
}


def _query_taboo(disease: str) -> dict:
    return {"disease": disease, "forbidden": _TABOO_TABLE.get(disease, [])}


disease_taboo_tool = StructuredTool.from_function(
    func=_query_taboo,
    name="disease_taboo",
    description="查询某种慢病的饮食禁忌清单。",
    args_schema=DiseaseTabooInput,
)
