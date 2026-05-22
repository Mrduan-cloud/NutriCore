"""Redis 客户端 — 用作会话缓存 / 限流 / 任务队列。"""
from __future__ import annotations

from functools import lru_cache
from loguru import logger
from redis.asyncio import Redis, from_url

from app.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    s = get_settings()
    return from_url(s.redis_url, encoding="utf-8", decode_responses=True)


async def is_healthy() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception as e:  # noqa: BLE001
        logger.warning("redis health failed: {}", e)
        return False
