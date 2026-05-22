"""多轮记忆：LLM Function Calling 抽取实体 → 增量合并入画像。"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.core.llm import chat_complete


class UserProfile(BaseModel):
    user_id: str
    age: int | None = None
    gender: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    chronic_diseases: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    diet_preferences: list[str] = Field(default_factory=list)
    budget_per_day: float | None = None
    pregnancy: bool = False
    medications: list[str] = Field(default_factory=list)

    def compute_bmi(self) -> float | None:
        if self.height_cm and self.weight_kg:
            h = self.height_cm / 100
            return round(self.weight_kg / (h * h), 2)
        return None


_EXTRACT_PROMPT = """请从用户消息中抽取个人画像字段。
只输出 JSON，字段为 null 表示未提及。可识别字段：
- age (int, 岁)
- gender ("male" / "female")
- height_cm (float)
- weight_kg (float)
- chronic_diseases (list[str])
- allergies (list[str])
- diet_preferences (list[str])
- budget_per_day (float, 元)
- pregnancy (bool)
- medications (list[str])

消息: {message}

只输出 JSON 对象，不要带任何解释。"""


def _safe_json(raw: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


async def extract_entities(message: str) -> dict[str, Any]:
    if not message or len(message) < 4:
        return {}
    try:
        raw = await chat_complete(
            _EXTRACT_PROMPT.format(message=message),
            response_format="json",
            temperature=0.0,
            max_tokens=400,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("entity extraction failed: {}", e)
        return {}
    return {k: v for k, v in _safe_json(raw).items() if v not in (None, [], "")}


async def merge_profile(existing: dict[str, Any], increment: dict[str, Any], user_id: str) -> dict[str, Any]:
    merged = dict(existing or {})
    merged.setdefault("user_id", user_id)
    for k, v in increment.items():
        if v in (None, [], ""):
            continue
        if isinstance(v, list) and isinstance(merged.get(k), list):
            merged[k] = list({*merged[k], *v})
        else:
            merged[k] = v
    profile = UserProfile.model_validate(merged)
    profile.bmi = profile.compute_bmi()
    return profile.model_dump()
