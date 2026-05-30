"""只重灌 Demo 业务数据(画像 + 时序),不动知识库(避免 Milvus 重复入库)。

包含两个演示人设:
- demo   : 男 / 32 / 高血压 / 清淡低钠(数据来自 seed CSV)
- xinxin : 女 / 27 / 素食低脂 / 减脂塑形(本文件内联生成)

用法:
    docker compose exec api python -m scripts.reseed_demo
"""
from __future__ import annotations

import asyncio
from datetime import date

from loguru import logger

from app.core.db import close_db, init_db
from app.observability.logging import setup_logging
from app.schemas.models import DailyIntake, UserProfileModel, Vitals
from scripts.seed import ROOT, seed_csv, seed_user

# ---------------- 林悦 人设(内联,无需额外 CSV) ----------------
XINXIN_PROFILE = {
    "user_id": "林悦",
    "age": 27,
    "gender": "female",
    "height_cm": 163,
    "weight_kg": 55,
    "chronic_diseases": [],
    "allergies": [],
    "diet_preferences": ["素食", "低脂"],
    "budget_per_day": 50,
    "pregnancy": False,
    "medications": [],
}

# (day, weight_kg, steps, sleep_hours)
XINXIN_VITALS = [
    (1, 55.2, 9200, 7.3), (2, 55.1, 8800, 7.1), (3, 55.0, 10100, 7.5),
    (4, 54.9, 9600, 6.9), (5, 54.9, 8900, 7.2), (6, 54.8, 11200, 7.4),
    (7, 54.7, 8700, 7.0), (8, 54.7, 9400, 7.6), (9, 54.6, 9000, 7.1),
    (10, 54.5, 9800, 7.3),
]

# (day, kcal, protein, carb, fat, water_ml)
XINXIN_INTAKE = [
    (1, 1620, 58, 210, 52, 1800), (2, 1550, 55, 198, 50, 1700),
    (3, 1680, 62, 218, 55, 1900), (4, 1500, 53, 190, 48, 1650),
    (5, 1600, 60, 205, 53, 1750), (6, 1580, 57, 200, 51, 1700),
    (7, 1650, 61, 212, 54, 1850), (8, 1520, 54, 192, 49, 1680),
    (9, 1640, 63, 208, 55, 1820), (10, 1570, 56, 199, 50, 1720),
]


async def _seed_profile(profile: dict) -> None:
    data = dict(profile)
    if data.get("height_cm") and data.get("weight_kg"):
        h = data["height_cm"] / 100
        data["bmi"] = round(data["weight_kg"] / (h * h), 2)
    uid = data["user_id"]
    defaults = {k: v for k, v in data.items() if k != "user_id"}
    await UserProfileModel.update_or_create(user_id=uid, defaults=defaults)


async def _seed_xinxin() -> None:
    await _seed_profile(XINXIN_PROFILE)
    for day, w, steps, sleep in XINXIN_VITALS:
        await Vitals.update_or_create(
            user_id="林悦", date=date(2026, 5, day),
            defaults={"weight_kg": w, "steps": steps, "sleep_hours": sleep},
        )
    for day, kcal, protein, carb, fat, water in XINXIN_INTAKE:
        await DailyIntake.update_or_create(
            user_id="林悦", date=date(2026, 5, day),
            defaults={"kcal": kcal, "protein": protein, "carb": carb,
                      "fat": fat, "water_ml": water},
        )
    logger.info("林悦 persona seeded (profile + {} days data)", len(XINXIN_VITALS))


async def main() -> None:
    setup_logging()
    await init_db()
    try:
        # demo(来自 seed CSV)
        await seed_user()
        await seed_csv(Vitals, ROOT / "app" / "data" / "seed" / "demo_vitals.csv")
        await seed_csv(DailyIntake, ROOT / "app" / "data" / "seed" / "demo_intake.csv")
        # xinxin(内联)
        await _seed_xinxin()
    finally:
        await close_db()
    logger.info("DEMO DATA RESEED DONE (demo + xinxin)")


if __name__ == "__main__":
    asyncio.run(main())
