"""健康数据洞察路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.data_insight.dify_client import run_workflow
from app.auth import CurrentUser, get_current_user

router = APIRouter()


class InsightRequest(BaseModel):
    question: str


@router.post("/query")
async def query_insight(
    payload: InsightRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        result = await run_workflow(payload.question, user.user_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"insight query failed: {e}") from e
    return result
