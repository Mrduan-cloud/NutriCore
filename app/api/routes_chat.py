"""AI 营养师对话路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.agents.nutritionist.graph import build_nutritionist_graph
from app.auth import CurrentUser, get_current_user
from app.schemas.models import UserProfileModel

router = APIRouter()

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_nutritionist_graph()
    return _graph


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[str] = []
    used_tools: list[str] = []
    is_high_risk: bool = False
    intent: str | None = None
    request_id: str | None = None


@router.post("/nutritionist", response_model=ChatResponse)
async def chat_with_nutritionist(
    payload: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    # 加载画像
    profile_row = await UserProfileModel.filter(user_id=user.user_id).first()
    profile = profile_row.to_dict() if profile_row else {"user_id": user.user_id}

    state = {
        "messages": [HumanMessage(content=payload.message)],
        "user_id": user.user_id,
        "user_profile": profile,
        "request_id": getattr(request.state, "request_id", None),
    }
    out = await _get_graph().ainvoke(state)

    # 画像写回
    if out.get("user_profile") and out["user_profile"] != profile:
        await UserProfileModel.update_from_dict(out["user_profile"])

    return ChatResponse(
        answer=out.get("final_answer") or "（无回复）",
        citations=out.get("citations") or [],
        used_tools=[c.get("tool") for c in out.get("tool_calls") or [] if c.get("tool")],
        is_high_risk=bool(out.get("is_high_risk")),
        intent=out.get("intent"),
        request_id=state["request_id"],
    )
