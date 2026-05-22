"""LangGraph 主控状态机：意图识别 → 子 Agent 路由 → 工具调用 → 引用核验 → 安全兜底。"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agents.nutritionist.nodes import (
    citation_validator,
    intent_router,
    memory_node,
    safety_fallback,
    subagent_dispatcher,
    tool_executor,
)


class NutritionistState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    user_profile: dict
    intent: str | None
    selected_subagent: str | None
    tool_calls: list[dict]
    citations: list[str]
    is_high_risk: bool
    final_answer: str | None
    extra: dict
    request_id: str


def _route(state: NutritionistState) -> Literal["high_risk", "subagent", "end"]:
    if state.get("is_high_risk"):
        return "high_risk"
    if state.get("selected_subagent"):
        return "subagent"
    return "end"


def build_nutritionist_graph():
    g = StateGraph(NutritionistState)
    g.add_node("memory", memory_node)
    g.add_node("intent_router", intent_router)
    g.add_node("subagent_dispatcher", subagent_dispatcher)
    g.add_node("tool_executor", tool_executor)
    g.add_node("citation_validator", citation_validator)
    g.add_node("safety_fallback", safety_fallback)

    g.add_edge(START, "memory")
    g.add_edge("memory", "intent_router")
    g.add_conditional_edges(
        "intent_router",
        _route,
        {"high_risk": "safety_fallback", "subagent": "subagent_dispatcher", "end": END},
    )
    g.add_edge("subagent_dispatcher", "tool_executor")
    g.add_edge("tool_executor", "citation_validator")
    g.add_edge("citation_validator", END)
    g.add_edge("safety_fallback", END)
    return g.compile()
