"""Tortoise-ORM 连接管理。"""
from __future__ import annotations

from loguru import logger
from tortoise import Tortoise

from app.config import get_settings

TORTOISE_CONFIG = {
    "connections": {"default": ""},  # 运行时填充
    "apps": {
        "models": {
            # 用 Tortoise.generate_schemas 自动建表,不依赖 aerich 迁移,
            # 所以这里不引用 aerich.models(否则未装 aerich 会 ConfigurationError)。
            "models": ["app.schemas.models"],
            "default_connection": "default",
        }
    },
    "use_tz": True,
    "timezone": "Asia/Shanghai",
}


async def init_db() -> None:
    s = get_settings()
    cfg = {**TORTOISE_CONFIG, "connections": {"default": s.mysql_dsn}}
    await Tortoise.init(config=cfg)
    await Tortoise.generate_schemas(safe=True)
    logger.info("database initialized ({}@{})", s.mysql_db, s.mysql_host)


async def close_db() -> None:
    await Tortoise.close_connections()


async def is_healthy() -> bool:
    try:
        conn = Tortoise.get_connection("default")
        await conn.execute_query("SELECT 1")
        return True
    except Exception as e:
        logger.warning("db health failed: {}", e)
        return False
