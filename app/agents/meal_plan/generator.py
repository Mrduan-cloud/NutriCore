"""7 天个性化营养方案生成主链 — 真实 LLM 调用 + 双层强约束校验。"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from loguru import logger

from app.agents.meal_plan.retriever import retrieve_plan_evidence
from app.agents.meal_plan.validator import validate_plan_strict
from app.core.llm import chat_complete
from app.observability.metrics import agent_invocations

_SYSTEM = """你是 NutriCore 营养方案生成器。你必须严格输出 JSON，结构如下：
{
  "user_id": "...",
  "plan_id": "...",
  "target_kcal": <number>,
  "days": [
    {"day": 1, "breakfast": [...], "lunch": [...], "dinner": [...], "snack": [...],
     "total_kcal": <number>, "macros": {"carb": 0.55, "protein": 0.18, "fat": 0.27}}
  ]
}
每个食材项形如：
{"name": "...", "portion_g": 120, "kcal": 180, "citations": ["doc_id:chunk_id"]}
约束：
- 必须 7 天 (day=1..7)
- 每日总热量在 target_kcal ±10% 内
- 碳水 50-60% / 蛋白质 15-20% / 脂肪 25-30%
- 不出现过敏 / 慢病忌口食材
- 每个食材必须带至少 1 条证据引用，格式 "doc_id:chunk_id"
"""


def _estimate_target_kcal(profile: dict[str, Any]) -> float:
    """简易 Mifflin-St Jeor TDEE 估算 — 缺失字段时给默认。"""
    g = (profile.get("gender") or "female").lower()
    age = int(profile.get("age") or 30)
    h = float(profile.get("height_cm") or 165)
    w = float(profile.get("weight_kg") or 60)
    activity = 1.4
    bmr = 10 * w + 6.25 * h - 5 * age + (5 if g == "male" else -161)
    return round(bmr * activity)


def _safe_json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("LLM 输出未发现 JSON 对象")
    return json.loads(m.group(0))


async def generate_meal_plan(
    user_profile: dict[str, Any],
    screening_result: dict[str, Any] | None = None,
    user_request: str = "请帮我生成 7 天个性化营养方案",
) -> dict[str, Any]:
    chronic = user_profile.get("chronic_diseases", []) or []
    allergies = user_profile.get("allergies", []) or []
    target_kcal = _estimate_target_kcal(user_profile)

    evidence = await retrieve_plan_evidence(
        query=user_request,
        chronic_diseases=chronic,
        allergies=allergies,
    )

    citations_block = "\n".join(
        f"[{e['doc_id']}:{e['chunk_id']}] {e['text'][:200]}" for e in evidence
    ) or "（无）"

    prompt = (
        f"用户画像：{json.dumps(user_profile, ensure_ascii=False)}\n"
        f"筛查结果：{json.dumps(screening_result or {}, ensure_ascii=False)}\n"
        f"目标日热量：{target_kcal} kcal\n"
        f"忌口（过敏+慢病）：{allergies + chronic}\n\n"
        f"可用证据（每条建议必须从以下证据中引用至少一条 [doc_id:chunk_id]）：\n"
        f"{citations_block}\n\n"
        f"请按 system 指令输出 7 天个性化方案 JSON。"
    )

    try:
        raw = await chat_complete(prompt, system=_SYSTEM, response_format="json", temperature=0.4)
        plan = _safe_json(raw)
    except Exception:
        logger.exception("LLM plan generation failed")
        agent_invocations.labels(agent="meal_plan", outcome="error").inc()
        raise

    plan.setdefault("user_id", user_profile.get("user_id", "anonymous"))
    plan.setdefault("plan_id", uuid.uuid4().hex)
    plan.setdefault("target_kcal", target_kcal)
    plan = validate_plan_strict(plan, evidence=evidence)
    agent_invocations.labels(agent="meal_plan", outcome="ok").inc()
    return plan
