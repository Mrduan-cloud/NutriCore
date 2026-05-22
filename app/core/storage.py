"""MinIO 对象存储封装。"""
from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from io import BytesIO

from loguru import logger
from minio import Minio
from minio.error import S3Error

from app.config import get_settings


@lru_cache(maxsize=1)
def _client() -> Minio:
    s = get_settings()
    return Minio(
        s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=s.minio_secure,
    )


def ensure_bucket() -> None:
    s = get_settings()
    c = _client()
    if not c.bucket_exists(s.minio_bucket):
        c.make_bucket(s.minio_bucket)
        logger.info("created MinIO bucket {}", s.minio_bucket)


async def upload_object(object_key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    s = get_settings()
    ensure_bucket()
    _client().put_object(
        s.minio_bucket,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_key


async def presigned_url(object_key: str, expire_seconds: int = 3600) -> str:
    s = get_settings()
    return _client().presigned_get_object(s.minio_bucket, object_key, expires=timedelta(seconds=expire_seconds))


def is_healthy() -> bool:
    try:
        ensure_bucket()
        return True
    except S3Error as e:
        logger.warning("MinIO health failed: {}", e)
        return False
