"""鉴权路由 —— 每用户独立口令(bcrypt)+ 失败锁定 + 角色化 JWT。

设计要点(相对早期「全局演示口令」的安全升级):
- 每个 ``username`` 有独立的 ``password_hash``,登录只校验**本人**口令,
  杜绝「知道一个口令就能冒充任意 user_id」的越权;
- 失败响应统一为 401,不区分「用户不存在 / 口令错」以防用户名枚举;
- 连续失败达到阈值即锁定一段时间,挡暴力撞库;
- 注册让用户自设口令(策略校验),不再共用一个口令;
- 演示人设走 ``/demo-accounts`` 暴露(仅 2 个 seed 账号),取代会泄露
  全部用户名的旧 ``/users`` 接口。

生产化路径(超出本 demo):刷新 token / OAuth-OIDC / 邮箱验证 / 多因素。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from tortoise.timezone import now as tz_now

from app.auth import create_access_token, hash_password, verify_password
from app.auth.security import (
    lock_state,
    next_locked_until,
    password_error,
    username_error,
)
from app.config import get_settings
from app.schemas.models import AuthAccount, UserProfileModel

router = APIRouter()

_INVALID_CREDENTIALS = "用户名或口令错误"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str = "user"


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


class RegisterResponse(BaseModel):
    user_id: str
    role: str = "user"
    access_token: str
    token_type: str = "bearer"


class DemoAccountsResponse(BaseModel):
    users: list[str]


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    """校验本人口令 → 失败锁定/计数 → 成功签发带角色的 JWT。"""
    s = get_settings()
    now_ts = time.time()  # 锁定判定用 UTC 纪元秒,避免 DATETIME 时区往返错位
    acct = await AuthAccount.filter(username=payload.username).first()

    # 用户不存在:仍返回统一 401(避免枚举)
    if acct is None:
        raise _unauthorized()

    if not acct.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="账号已被停用,请联系管理员"
        )

    ls = lock_state(acct.locked_until_ts, now_ts)
    if ls.locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录失败次数过多,请 {ls.retry_after_minutes} 分钟后再试",
        )

    if not verify_password(payload.password, acct.password_hash):
        acct.failed_attempts += 1
        acct.locked_until_ts = next_locked_until(
            acct.failed_attempts, s.auth_max_failed_attempts, s.auth_lockout_minutes, now_ts
        )
        await acct.save(update_fields=["failed_attempts", "locked_until_ts"])
        raise _unauthorized()

    # 成功:清零失败计数 + 记录登录时间(last_login_at 仅展示用,沿用 DATETIME)
    acct.failed_attempts = 0
    acct.locked_until_ts = None
    acct.last_login_at = tz_now()
    await acct.save(update_fields=["failed_attempts", "locked_until_ts", "last_login_at"])

    # 保证画像存在(登录即可用)
    await UserProfileModel.get_or_create(user_id=acct.username)

    token = create_access_token(user_id=acct.username, role=acct.role)
    return LoginResponse(access_token=token, user_id=acct.username, role=acct.role)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> RegisterResponse:
    """自助注册:用户名/口令策略校验 → 创建独立凭证 → 直接签发 token(自动登录)。"""
    uerr = username_error(payload.username)
    if uerr:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=uerr)
    perr = password_error(payload.password)
    if perr:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=perr)

    if await AuthAccount.filter(username=payload.username).exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    await AuthAccount.create(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role="user",
    )
    await UserProfileModel.get_or_create(user_id=payload.username)

    token = create_access_token(user_id=payload.username, role="user")
    return RegisterResponse(user_id=payload.username, role="user", access_token=token)


@router.get("/demo-accounts", response_model=DemoAccountsResponse)
async def demo_accounts() -> DemoAccountsResponse:
    """仅返回演示人设(is_demo),供登录页快速体验。不暴露真实用户名。"""
    rows = await AuthAccount.filter(is_demo=True).values_list("username", flat=True)
    return DemoAccountsResponse(users=list(rows))
