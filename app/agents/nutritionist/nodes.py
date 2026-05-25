"""主控状态机节点 — 真实意图识别 + 子 Agent 派发 + 引用核验 + 兜底。"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.agents.nutritionist.memory import extract_entities, merge_profile
from app.agents.nutritionist.prompts import INTENT_PROMPT
from app.core.llm import chat_complete
from app.observability.metrics import agent_invocations


HIGH_RISK_KEYWORDS = (
    "急救", "胸痛", "昏迷", "孕妇", "怀孕", "孕期", "化疗", "透析",
    "晕厥", "脑梗", "心梗", "出血",
)

INTENT_TO_AGENT = {
    "screening": "risk_screening",
    "plan": "meal_plan",
    "insight": "data_insight",
    "consult": None,
}


def _is_high_risk(text: str) -> bool:
    return any(k in text for k in HIGH_RISK_KEYWORDS)


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def _last_user_text(state: dict[str, Any]) -> str:
    for msg in reversed(state.get("messages", [])):
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")
        if content:
            return content
    return ""


async def intent_router(state: dict[str, Any]) -> dict[str, Any]:
    last_msg = _last_user_text(state)
    if _is_high_risk(last_msg):
        agent_invocations.labels(agent="intent_router", outcome="high_risk").inc()
        return {"intent": "risk_alert", "selected_subagent": None, "is_high_risk": True}

    try:
        raw = await chat_complete(
            INTENT_PROMPT.format(user_message=last_msg),
            response_format="json",
            temperature=0.0,
            max_tokens=200,
        )
        intent = _extract_json(raw).get("intent", "consult")
    except Exception as e:  # noqa: BLE001
        logger.warning("intent classify failed, fallback to consult: {}", e)
        intent = "consult"

    sub = INTENT_TO_AGENT.get(intent)
    agent_invocations.labels(agent="intent_router", outcome=intent).inc()
    return {"intent": intent, "selected_subagent": sub, "is_high_risk": False}


async def subagent_dispatcher(state: dict[str, Any]) -> dict[str, Any]:
    sub = state.get("selected_subagent")
    user_id = state.get("user_id", "anonymous")
    profile = state.get("user_profile", {})
    last_msg = _last_user_text(state)

    if sub == "risk_screening":
        return {
            "final_answer": "请打开「营养风险筛查」入口完成 NRS2002 问卷，我会基于结果给你详细解读。",
            "tool_calls": [{"tool": "risk_screening_intro"}],
        }

    if sub == "meal_plan":
        from app.agents.meal_plan.generator import generate_meal_plan
        try:
            plan = await generate_meal_plan(profile, user_request=last_msg)
            return {
                "final_answer": "已为你生成 7 天个性化营养方案，可在「方案中心」查看。",
                "tool_calls": [{"tool": "meal_plan.generate"}],
                "citations": _collect_citations(plan),
            }
        except Exception as e:  # noqa: BLE001
            logger.exception("meal_plan failed")
            return {"final_answer": f"方案生成失败：{e}"}

    if sub == "data_insight":
        from app.agents.data_insight.dify_client import run_workflow
        try:
            result = await run_workflow(last_msg, user_id)
            return {
                "final_answer": "已查询并生成可视化，可在「数据洞察」面板查看。",
                "tool_calls": [{"tool": "data_insight.query"}],
                "extra": {"insight": result},
            }
        except Exception as e:  # noqa: BLE001
            logger.exception("data_insight failed")
            return {"final_answer": f"数据查询失败：{e}"}

    # 未知子 Agent (理论上不可达 —— _route 已经在前面短路掉 sub=None)
    return {"final_answer": f"未配置的子 Agent: {sub!r}"}


async def tool_executor(state: dict[str, Any]) -> dict[str, Any]:
    """工具调用审计 — 把 dispatcher 写入的 tool_calls 落审计日志。

    本节点目前是 audit-only(真实工具执行已由 dispatcher 完成),
    但仍必须返回非空 patch,否则 LangGraph 会抛 InvalidUpdateError
    (要求节点至少写入一个 schema 字段)—— 这里回写 tool_calls 自身作为 noop。
    """
    user_id = state.get("user_id", "anonymous")
    rid = state.get("request_id", "-")
    tool_calls = state.get("tool_calls", []) or []
    for call in tool_calls:
        logger.bind(audit=True, request_id=rid, user_id=user_id).info(
            "tool_call name={}", call.get("tool")
        )
    return {"tool_calls": tool_calls}


async def citation_validator(state: dict[str, Any]) -> dict[str, Any]:
    citations = state.get("citations", []) or []
    valid = [c for c in citations if isinstance(c, str) and ":" in c]
    return {"citations": valid}


async def safety_fallback(state: dict[str, Any]) -> dict[str, Any]:
    fallback = (
        "你描述的情况涉及较高健康风险（如用药 / 急重症 / 孕产期），"
        "营养方案不是合适的干预手段。建议尽快前往专科医院由临床医生评估处理。\n"
        "如果是非紧急的日常营养咨询，可以补充说明你的具体场景，我再帮你判断。"
    )
    agent_invocations.labels(agent="safety_fallback", outcome="triggered").inc()
    return {"final_answer": fallback, "is_high_risk": True}


async def memory_node(state: dict[str, Any]) -> dict[str, Any]:
    """从用户消息抽取画像字段并增量合入 user_profile。

    抽取失败 / 无新字段时,仍要返回带 user_profile 的 patch
    (LangGraph 节点不能返回空 dict —— 会抛 InvalidUpdateError)。
    """
    existing = state.get("user_profile", {})
    last_msg = _last_user_text(state)
    increment = await extract_entities(last_msg)
    if increment:
        merged = await merge_profile(
            existing, increment, user_id=state.get("user_id", "")
        )
        return {"user_profile": merged}
    # noop:回写既有 profile 满足 channel 写入要求
    return {"user_profile": existing}


def _collect_citations(plan: dict) -> list[str]:
    out: list[str] = []
    for day in plan.get("days", []) or []:
        for slot in ("breakfast", "lunch", "dinner", "snack"):
            for item in day.get(slot, []) or []:
                out.extend(item.get("citations", []))
    return list(dict.fromkeys(out))
