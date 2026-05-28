"""只重灌 Demo 业务数据(画像 + 时序),不动知识库(避免 Milvus 重复入库)。

用途:demo 账号的 user_id 统一/数据修订后,快速把 demo_user.json /
demo_vitals.csv / demo_intake.csv 重新写入 MySQL,而不触发 KB 再 ingest。

用法:
    docker compose exec api python -m scripts.reseed_demo
"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.core.db import close_db, init_db
from app.observability.logging import setup_logging
from app.schemas.models import DailyIntake, Vitals
from scripts.seed import ROOT, seed_csv, seed_user


async def main() -> None:
    setup_logging()
    await init_db()
    try:
        await seed_user()
        await seed_csv(Vitals, ROOT / "app" / "data" / "seed" / "demo_vitals.csv")
        await seed_csv(DailyIntake, ROOT / "app" / "data" / "seed" / "demo_intake.csv")
    finally:
        await close_db()
    logger.info("DEMO DATA RESEED DONE")


if __name__ == "__main__":
    asyncio.run(main())
