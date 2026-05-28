"""鉴权路由 —— 演示级登录,签发 JWT。

NutriCore 的数据模型以 ``user_id`` 为中心,没有独立的密码表(这是 mock
项目的有意简化)。这里提供一个**演示级**登录:
- 用统一的演示口令(``DEMO_PASSWORD``,默认 ``demo123``)做最小门槛,
  避免任何人裸拿 token;
- 登录即按 ``username`` 作为 ``user_id`` 自动建档(get_or_create),
  所以无需单独的注册流程,直接登录即用;
- 成功签发 JWT,前端后续请求带 ``Authorization: Bearer <token>``。

生产化路径(超出本 demo 范围):接入独立用户表 + bcrypt 口令 +
刷新 token + OAuth/OIDC。
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import create_access_token
from app.schemas.models import UserProfileModel

router = APIRouter()

# 演示口令:本地/面试演示用。改成自己的可在 .env 里加 DEMO_PASSWORD=...
_DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "nutricore2024")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="用作 user_id")
    password: str = Field(..., description="演示口令(默认 demo123)")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    """演示登录:校验演示口令 → 按 username 建档 → 签发 JWT。"""
    if payload.password != _DEMO_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或口令错误(演示口令默认 demo123)",
        )

    # 按 username 作为 user_id 建档(已存在则直接复用),保证登录后画像可用
    await UserProfileModel.get_or_create(user_id=payload.username)

    token = create_access_token(user_id=payload.username)
    return LoginResponse(access_token=token, user_id=payload.username)
