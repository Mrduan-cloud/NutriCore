"""鉴权:JWT + 角色守卫 + 口令哈希。"""
from app.auth.jwt import (
    CurrentUser,
    create_access_token,
    decode_token,
    get_current_user,
    require_admin,
)
from app.auth.passwords import hash_password, verify_password

__all__ = [
    "CurrentUser",
    "create_access_token",
    "decode_token",
    "get_current_user",
    "hash_password",
    "require_admin",
    "verify_password",
]
