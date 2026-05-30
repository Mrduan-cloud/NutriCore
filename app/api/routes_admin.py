"""管理后台路由 —— 全部受 ``require_admin`` 守卫(JWT 角色 = admin)。

提供账号生命周期管理:列表 / 新建 / 重置口令 / 启停 / 改角色 / 删除,
并落审计日志(AuditLog)。内置安全护栏:不能把自己锁死,也不能删/降级
最后一个管理员,避免把系统管成「无人可管」。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import CurrentUser, hash_password, require_admin
from app.auth.security import password_error, username_error
from app.schemas.models import AuditLog, AuthAccount, UserProfileModel

router = APIRouter()

_ADMIN = "admin"


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)
    role: str = Field("user", pattern="^(user|admin)$")


class ResetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


class UpdateUserRequest(BaseModel):
    role: str | None = Field(None, pattern="^(user|admin)$")
    is_active: bool | None = None
    unlock: bool = False  # 清除失败锁定


class UsersResponse(BaseModel):
    users: list[dict]


async def _audit(admin_id: str, action: str, target: str, **extra) -> None:
    await AuditLog.create(
        request_id=uuid.uuid4().hex,
        user_id=admin_id,
        action=action,
        payload={"target": target, **extra},
    )


async def _admin_count() -> int:
    return await AuthAccount.filter(role=_ADMIN, is_active=True).count()


async def _get_or_404(username: str) -> AuthAccount:
    acct = await AuthAccount.filter(username=username).first()
    if acct is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return acct


@router.get("/users", response_model=UsersResponse)
async def list_users(admin: Annotated[CurrentUser, Depends(require_admin)]) -> UsersResponse:
    rows = await AuthAccount.all().order_by("role", "-created_at")
    return UsersResponse(users=[a.to_admin_view() for a in rows])


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest, admin: Annotated[CurrentUser, Depends(require_admin)]
) -> dict:
    uerr = username_error(payload.username)
    if uerr:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=uerr)
    perr = password_error(payload.password)
    if perr:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=perr)
    if await AuthAccount.filter(username=payload.username).exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    acct = await AuthAccount.create(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    await UserProfileModel.get_or_create(user_id=payload.username)
    await _audit(admin.user_id, "admin.create_user", payload.username, role=payload.role)
    return acct.to_admin_view()


@router.post("/users/{username}/reset-password")
async def reset_password(
    username: str,
    payload: ResetPasswordRequest,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> dict:
    perr = password_error(payload.password)
    if perr:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=perr)
    acct = await _get_or_404(username)
    acct.password_hash = hash_password(payload.password)
    acct.failed_attempts = 0
    acct.locked_until_ts = None
    await acct.save(update_fields=["password_hash", "failed_attempts", "locked_until_ts"])
    await _audit(admin.user_id, "admin.reset_password", username)
    return {"ok": True}


@router.patch("/users/{username}")
async def update_user(
    username: str,
    payload: UpdateUserRequest,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> dict:
    acct = await _get_or_404(username)
    is_self = username == admin.user_id

    # 降级最后一个管理员 → 拒绝(避免无人可管)
    if payload.role == "user" and acct.role == _ADMIN and await _admin_count() <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能降级最后一个管理员")
    # 停用自己 / 停用最后一个管理员 → 拒绝
    if payload.is_active is False:
        if is_self:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能停用自己")
        if acct.role == _ADMIN and await _admin_count() <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="不能停用最后一个管理员"
            )

    fields: list[str] = []
    if payload.role is not None and payload.role != acct.role:
        acct.role = payload.role
        fields.append("role")
    if payload.is_active is not None and payload.is_active != acct.is_active:
        acct.is_active = payload.is_active
        fields.append("is_active")
    if payload.unlock:
        acct.failed_attempts = 0
        acct.locked_until_ts = None
        fields += ["failed_attempts", "locked_until_ts"]

    if fields:
        await acct.save(update_fields=list(set(fields)))
        await _audit(admin.user_id, "admin.update_user", username, fields=fields)
    return acct.to_admin_view()


@router.delete("/users/{username}")
async def delete_user(
    username: str, admin: Annotated[CurrentUser, Depends(require_admin)]
) -> dict:
    acct = await _get_or_404(username)
    if username == admin.user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能删除自己")
    if acct.role == _ADMIN and await _admin_count() <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能删除最后一个管理员")
    await acct.delete()
    await _audit(admin.user_id, "admin.delete_user", username)
    return {"ok": True}
