"""一键初始化全栈：MySQL 表 + Milvus 集合 + 知识库 + Demo 用户数据。

用法：
    python -m scripts.seed
"""
from __future__ import annotations

import asyncio
import csv
import json
from datetime import date as date_t
from pathlib import Path

from loguru import logger

from app.config import get_settings
from app.core.db import close_db, init_db
from app.core.storage import ensure_bucket
from app.observability.logging import setup_logging
from app.rag.ingestion import ingest_markdown_dir
from app.schemas.models import DailyIntake, UserProfileModel, Vitals


ROOT = Path(__file__).resolve().parents[1]


async def seed_kb() -> None:
    s = get_settings()
    n = await ingest_markdown_dir(
        ROOT / "app" / "data" / "kb",
        collection=s.milvus_collection_guide,
        base_metadata={"source": "seed"},
    )
    logger.info("KB seed done, {} chunks", n)


async def seed_user() -> None:
    profile_path = ROOT / "app" / "data" / "seed" / "demo_user.json"
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    if data["height_cm"] and data["weight_kg"]:
        h = data["height_cm"] / 100
        data["bmi"] = round(data["weight_kg"] / (h * h), 2)
    await UserProfileModel.update_or_create(user_id=data["user_id"], defaults=data)
    logger.info("demo profile seeded -> {}", data["user_id"])


async def seed_csv(model, path: Path, date_field: str = "date") -> None:
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row[date_field] = date_t.fromisoformat(row[date_field])
            for k, v in list(row.items()):
                if k not in {"user_id", date_field} and v != "":
                    row[k] = float(v) if "." in v else int(v)
            await model.update_or_create(
                user_id=row["user_id"], **{date_field: row[date_field]},
                defaults=row,
            )
    logger.info("seeded {} from {}", model.__name__, path.name)


async def main() -> None:
    setup_logging()
    ensure_bucket()
    await init_db()
    try:
        await seed_user()
        await seed_csv(Vitals, ROOT / "app" / "data" / "seed" / "demo_vitals.csv")
        await seed_csv(DailyIntake, ROOT / "app" / "data" / "seed" / "demo_intake.csv")
        await seed_kb()
    finally:
        await close_db()
    logger.info("ALL SEED DONE")


if __name__ == "__main__":
    asyncio.run(main())
