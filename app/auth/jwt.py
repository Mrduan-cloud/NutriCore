"""JWT 鉴权封装。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.config import get_settings


class CurrentUser(BaseModel):
    user_id: str
    role: str = "user"


def create_access_token(user_id: str, role: str = "user", expires_minutes: int | None = None) -> str:
    s = get_settings()
    expire = datetime.now(UTC) + timedelta(
        minutes=expires_minutes or s.jwt_access_token_expire_minutes
    )
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> CurrentUser:
    s = get_settings()
    try:
        data = jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from e
    return CurrentUser(user_id=data["sub"], role=data.get("role", "user"))


async def get_current_user(authorization: Annotated[str | None, Header()] = None) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing Bearer token")
    return decode_token(authorization[7:])


async def require_admin(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    """管理员守卫:JWT 角色非 admin 一律 403。"""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
