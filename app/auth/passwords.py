"""口令哈希 —— bcrypt 直连。

两个有意的工程选择:
1. 不经 passlib:规避 passlib 1.7.x 读取 bcrypt 4.x ``__about__`` 触发的
   AttributeError(社区常见坑),直接用 bcrypt 库更稳。
2. 先 sha256 预散列再 base64:bcrypt 只取前 72 字节、超长静默截断;预散列
   把任意长度口令压成 44 字节的稳定串,既避开截断又支持长口令。
"""
from __future__ import annotations

import base64
import hashlib

import bcrypt


def _prehash(raw: str) -> bytes:
    digest = hashlib.sha256((raw or "").encode("utf-8")).digest()
    return base64.b64encode(digest)  # 44 字节,远小于 bcrypt 的 72 上限


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(_prehash(raw), bcrypt.gensalt()).decode("ascii")


def verify_password(raw: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_prehash(raw), hashed.encode("ascii"))
    except (ValueError, TypeError):
        # 哈希串损坏 / 非法编码:按校验失败处理,不抛
        return False
