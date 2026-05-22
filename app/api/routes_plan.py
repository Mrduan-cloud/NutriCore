"""个性化营养方案路由。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.meal_plan.generator import generate_meal_plan
from app.agents.meal_plan.pdf_export import export_meal_plan_pdf
from app.auth import CurrentUser, get_current_user
from app.core.storage import presigned_url
from app.schemas.models import MealPlanRecord, UserProfileModel

router = APIRouter()


class PlanRequest(BaseModel):
    user_profile: dict[str, Any] | None = None
    screening_result: dict[str, Any] | None = None
    user_request: str = "请帮我生成 7 天个性化营养方案"


@router.post("/generate")
async def gen_plan(
    payload: PlanRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    # 优先用传入画像，否则查库
    profile = payload.user_profile
    if not profile:
        prow = await UserProfileModel.filter(user_id=user.user_id).first()
        profile = prow.to_dict() if prow else {"user_id": user.user_id}
    profile.setdefault("user_id", user.user_id)

    try:
        plan = await generate_meal_plan(profile, payload.screening_result, payload.user_request)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"plan generation failed: {e}") from e

    pdf_key = await export_meal_plan_pdf(plan, user.user_id)
    await MealPlanRecord.create(
        user_id=user.user_id,
        plan_id=plan.get("plan_id", ""),
        target_kcal=plan.get("target_kcal", 0),
        pdf_object_key=pdf_key,
        payload=plan,
    )
    return {"plan": plan, "pdf_object_key": pdf_key}


@router.get("/{plan_id}/pdf")
async def plan_pdf(plan_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    rec = await MealPlanRecord.filter(plan_id=plan_id, user_id=user.user_id).first()
    if not rec:
        raise HTTPException(404, "plan not found")
    url = await presigned_url(rec.pdf_object_key)
    return {"download_url": url}
