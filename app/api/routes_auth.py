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
import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import create_access_token
from app.schemas.models import UserProfileModel

router = APIRouter()

# 演示口令:本地/面试演示用。改成自己的可在 .env 里加 DEMO_PASSWORD=...
_DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "nutricore2024")

# 新建用户名约束:字母/数字/下划线/连字符,1-32 位。登录沿用更宽松的规则
# (老账号可能含别的字符),只在「显式新建」时收紧,避免脏 user_id 进库。
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="用作 user_id")
    password: str = Field(..., description="演示口令(默认 demo123)")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32, description="新用户名 = user_id")
    password: str = Field(..., description="演示口令(防止开放注册被刷)")


class RegisterResponse(BaseModel):
    user_id: str
    created: bool


class UsersResponse(BaseModel):
    users: list[str]


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


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest) -> RegisterResponse:
    """新建用户:校验演示口令 + 用户名格式 → get_or_create 画像。

    登录本身就会自动建档,所以注册不是登录的前置;它的价值是让前端能
    「显式添加」一个用户(并出现在用户列表里),用户名也在此处统一收紧。
    """
    if payload.password != _DEMO_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="演示口令错误,无法创建用户",
        )
    if not _USERNAME_RE.match(payload.username):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="用户名仅支持字母 / 数字 / 下划线 / 连字符,长度 1-32",
        )
    _, created = await UserProfileModel.get_or_create(user_id=payload.username)
    return RegisterResponse(user_id=payload.username, created=created)


@router.get("/users", response_model=UsersResponse)
async def list_users() -> UsersResponse:
    """列出已有用户(供登录页快速选择)。演示级,最多返回最近更新的 50 个。"""
    rows = (
        await UserProfileModel.all()
        .order_by("-updated_at")
        .limit(50)
        .values_list("user_id", flat=True)
    )
    return UsersResponse(users=list(rows))
