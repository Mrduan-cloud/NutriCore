"""用户画像 CRUD 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.schemas.models import UserProfileModel

router = APIRouter()


class ProfileIn(BaseModel):
    age: int | None = None
    gender: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    chronic_diseases: list[str] = []
    allergies: list[str] = []
    diet_preferences: list[str] = []
    budget_per_day: float | None = None
    pregnancy: bool = False
    medications: list[str] = []


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)) -> dict:
    row = await UserProfileModel.filter(user_id=user.user_id).first()
    return row.to_dict() if row else {"user_id": user.user_id}


@router.put("/me")
async def upsert_me(payload: ProfileIn, user: CurrentUser = Depends(get_current_user)) -> dict:
    data = payload.model_dump()
    data["user_id"] = user.user_id
    if data["height_cm"] and data["weight_kg"]:
        h = data["height_cm"] / 100
        data["bmi"] = round(data["weight_kg"] / (h * h), 2)
    obj, _ = await UserProfileModel.update_or_create(user_id=user.user_id, defaults=data)
    return obj.to_dict()
