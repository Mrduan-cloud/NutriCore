"""多轮记忆：

- **短期记忆**（本文件上半部）：Redis 里按 (user, session) 滚动保存最近 N 轮对话,
  让 Agent 跨请求记住上下文(多轮筛查 / 追问)。后端有状态,不依赖前端回传历史。
- **长期画像**（下半部）：LLM 抽取实体 → 增量合并入 MySQL UserProfile。
"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.core.cache import get_redis
from app.core.llm import chat_complete

# ============================================================
# 短期记忆（Redis-backed short-term memory）
# ============================================================
#
# 设计:
# - 一“轮”= 一条用户消息 + 一条助手回复(2 条 message)。保留最近 6 轮 = 12 条。
# - 存为 Redis List(RPUSH 追加 → 时间正序),每个元素是 {"role","content"} 的 JSON。
# - 每次写入后 LTRIM 截到末尾 12 条 + 续期 TTL(无活动 2 小时后自动过期,不留垃圾)。
# - **韧性优先**:任何 Redis 异常都降级为「无记忆」(返回 []/静默跳过),
#   对话主链路绝不能因为缓存挂掉而 500。
STM_MAX_TURNS = 6
STM_TTL_SECONDS = 2 * 60 * 60
_STM_PREFIX = "nutricore:stm"
_VALID_ROLES = ("user", "assistant")


def _stm_key(user_id: str, session_id: str | None) -> str:
    return f"{_STM_PREFIX}:{user_id or 'anon'}:{session_id or 'default'}"


async def recent_turns(
    user_id: str, session_id: str | None, *, max_turns: int = STM_MAX_TURNS
) -> list[dict[str, str]]:
    """读取最近 ``max_turns`` 轮对话,返回 [{role, content}, ...](时间正序)。

    Redis 不可用 / 数据损坏时返回 [](降级为无记忆),不抛错。
    """
    key = _stm_key(user_id, session_id)
    try:
        raw = await get_redis().lrange(key, -2 * max_turns, -1)
    except Exception as e:
        logger.debug("short-term memory read failed ({}), degrade to no-memory", e)
        return []
    out: list[dict[str, str]] = []
    for item in raw or []:
        try:
            obj = json.loads(item)
        except (json.JSONDecodeError, TypeError):
            continue
        role, content = obj.get("role"), obj.get("content")
        if role in _VALID_ROLES and isinstance(content, str) and content:
            out.append({"role": role, "content": content})
    return out


async def remember_turn(
    user_id: str,
    session_id: str | None,
    user_msg: str,
    assistant_msg: str,
    *,
    max_turns: int = STM_MAX_TURNS,
) -> None:
    """把一轮(用户 + 助手)追加进短期记忆,并截断到最近 ``max_turns`` 轮 + 续期 TTL。

    Redis 不可用时静默跳过(不影响本次对话已经产出的回答)。
    """
    user_msg = (user_msg or "").strip()
    assistant_msg = (assistant_msg or "").strip()
    if not user_msg or not assistant_msg:
        return
    key = _stm_key(user_id, session_id)
    payload = [
        json.dumps({"role": "user", "content": user_msg}, ensure_ascii=False),
        json.dumps({"role": "assistant", "content": assistant_msg}, ensure_ascii=False),
    ]
    try:
        r = get_redis()
        await r.rpush(key, *payload)
        await r.ltrim(key, -2 * max_turns, -1)
        await r.expire(key, STM_TTL_SECONDS)
    except Exception as e:
        logger.debug("short-term memory write failed ({}), skipped", e)


async def clear_short_term(user_id: str, session_id: str | None) -> None:
    """清空某会话的短期记忆(新开对话 / 显式重置时可调用)。"""
    try:
        await get_redis().delete(_stm_key(user_id, session_id))
    except Exception as e:
        logger.debug("short-term memory clear failed ({}), ignored", e)


# ============================================================
# 长期画像（LLM 实体抽取 → 增量合并）
# ============================================================


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
    except Exception as e:
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
