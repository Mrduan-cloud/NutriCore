"""AI 营养师对话路由。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agents.nutritionist.graph import build_nutritionist_graph
from app.agents.nutritionist.nodes import (
    build_consult_prompt,
    intent_router,
    safety_fallback,
    subagent_dispatcher,
)
from app.agents.nutritionist.prompts import CONSULT_SYSTEM
from app.auth import CurrentUser, get_current_user
from app.core.llm import chat_complete_stream
from app.schemas.models import UserProfileModel

router = APIRouter()

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_nutritionist_graph()
    return _graph


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    # 最近若干轮对话历史(前端传入),用于多轮场景(如 NRS-2002 续轮筛查)
    history: list[ChatTurn] | None = None


def _build_messages(payload: ChatRequest) -> list:
    """把历史 + 当前消息组装成 LangChain 消息序列(最多保留最近 12 轮历史)。"""
    msgs: list = []
    for turn in (payload.history or [])[-12:]:
        content = (turn.content or "").strip()
        if not content:
            continue
        if turn.role == "assistant":
            msgs.append(AIMessage(content=content))
        else:
            msgs.append(HumanMessage(content=content))
    msgs.append(HumanMessage(content=payload.message))
    return msgs


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
        "messages": _build_messages(payload),
        "user_id": user.user_id,
        "user_profile": profile,
        "request_id": getattr(request.state, "request_id", None),
    }
    out = await _get_graph().ainvoke(state)

    # 画像写回
    if out.get("user_profile") and out["user_profile"] != profile:
        await UserProfileModel.upsert_from_dict(out["user_profile"])

    return ChatResponse(
        answer=out.get("final_answer") or "（无回复）",
        citations=out.get("citations") or [],
        used_tools=[c.get("tool") for c in out.get("tool_calls") or [] if c.get("tool")],
        is_high_risk=bool(out.get("is_high_risk")),
        intent=out.get("intent"),
        request_id=state["request_id"],
    )


def _sse(obj: dict) -> str:
    """打包一条 SSE 事件。"""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/nutritionist/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """SSE 流式对话:

    - consult(一般咨询)→ 逐 token 真流式(打字机)
    - 高风险 / plan / screening / insight → 复用既有节点产出结果,分块发出

    事件类型:
      {"type":"meta", intent, is_high_risk}     首包,前端立刻显示意图标签
      {"type":"delta","content":"..."}           增量文本
      {"type":"done", citations, used_tools}     收尾
      {"type":"error","message":"..."}           出错
    """
    profile_row = await UserProfileModel.filter(user_id=user.user_id).first()
    profile = profile_row.to_dict() if profile_row else {"user_id": user.user_id}
    state = {
        "messages": _build_messages(payload),
        "user_id": user.user_id,
        "user_profile": profile,
        "request_id": getattr(request.state, "request_id", None),
    }

    async def gen():
        try:
            # 1. 路由(高风险 gate + 规则 + LLM 意图分类)
            routing = await intent_router(state)
            state.update(routing)
            intent = routing.get("intent")
            is_high_risk = bool(routing.get("is_high_risk"))
            yield _sse({"type": "meta", "intent": intent, "is_high_risk": is_high_risk})

            # 2. 高风险 → 安全兜底(分块发)
            if is_high_risk:
                out = await safety_fallback(state)
                for piece in _chunks(out.get("final_answer", "")):
                    yield _sse({"type": "delta", "content": piece})
                yield _sse({"type": "done", "citations": [], "used_tools": []})
                return

            # 3. 命中子 Agent(plan/screening/insight)→ 跑子 Agent,结果分块发
            if routing.get("selected_subagent"):
                out = await subagent_dispatcher(state)
                for piece in _chunks(out.get("final_answer", "")):
                    yield _sse({"type": "delta", "content": piece})
                used = [c.get("tool") for c in out.get("tool_calls") or [] if c.get("tool")]
                done = {
                    "type": "done",
                    "citations": out.get("citations") or [],
                    "used_tools": used,
                }
                # 数据洞察:把 ECharts 配置随 done 事件下发,前端渲染图表
                chart = ((out.get("extra") or {}).get("insight") or {}).get("echarts_option")
                if isinstance(chart, dict) and not chart.get("noData"):
                    done["chart"] = chart
                yield _sse(done)
                return

            # 4. consult → RAG 检索接地 + 真·逐 token 流式
            #    先检索(拿到真实引用),再流式作答,引用在 done 事件回传
            prompt, citations = await build_consult_prompt(payload.message, profile)
            async for tok in chat_complete_stream(
                prompt, system=CONSULT_SYSTEM, temperature=0.3, max_tokens=600
            ):
                yield _sse({"type": "delta", "content": tok})
            yield _sse({"type": "done", "citations": citations, "used_tools": []})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": f"服务暂时不可用:{e.__class__.__name__}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chunks(text: str, size: int = 24):
    """把整段文本切成小块,模拟流式(给非 LLM-流式的结果用)。"""
    for i in range(0, len(text), size):
        yield text[i : i + size]
