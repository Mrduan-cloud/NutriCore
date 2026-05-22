"""健康检查路由 — 区分 liveness / readiness。

- /health  : liveness, 进程存活即可（Docker HEALTHCHECK）
- /ready   : readiness, 检查 DB / Milvus / MinIO / Redis 全部就绪
"""
from __future__ import annotations

from fastapi import APIRouter

from app.clients import milvus as milvus_client
from app.clients import redis_client
from app.core.db import is_healthy as db_healthy
from app.core.storage import is_healthy as storage_healthy

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    db = await db_healthy()
    redis = await redis_client.is_healthy()
    milvus = milvus_client.is_healthy()
    minio = storage_healthy()
    all_ok = all([db, redis, milvus, minio])
    return {
        "ready": all_ok,
        "checks": {"db": db, "redis": redis, "milvus": milvus, "minio": minio},
    }
