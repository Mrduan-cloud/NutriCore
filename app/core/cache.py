"""Redis 异步客户端 — 短期记忆 / 缓存共用。

与 core/llm.py 的客户端一致用 ``lru_cache`` 单例;``decode_responses=True``
让取回的是 str 而非 bytes,JSON 解析更省事。
"""
from __future__ import annotations

from functools import lru_cache

import redis.asyncio as aioredis

from app.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> aioredis.Redis:
    s = get_settings()
    return aioredis.from_url(
        s.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
