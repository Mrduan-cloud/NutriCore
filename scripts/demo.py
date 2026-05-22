"""端到端 demo：颁发 JWT → 提交 NRS2002 → 生成方案 → 数据洞察。

用法（API 已起来）：
    python -m scripts.demo --base-url http://localhost:8000 --user demo-001
"""
from __future__ import annotations

import argparse
import asyncio
import json

import httpx

from app.auth.jwt import create_access_token


SAMPLE_NRS = {
    "age": 32,
    "bmi": 25.5,
    "weight_loss_pct_3m": 1.5,
    "food_intake_drop_pct": 10,
    "disease_severity": 0,
}


async def run(base_url: str, user: str) -> None:
    token = create_access_token(user)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=120) as client:

        print("== /ready ==")
        r = await client.get("/ready")
        print(r.status_code, r.text[:200])

        print("\n== /api/screening/nrs2002 ==")
        r = await client.post("/api/screening/nrs2002", json=SAMPLE_NRS)
        print(r.status_code, r.text[:300])

        print("\n== /api/plan/generate ==")
        r = await client.post("/api/plan/generate", json={"user_request": "我想减脂，请给我 7 天方案"})
        print(r.status_code, str(r.json())[:400])

        print("\n== /api/insight/query ==")
        r = await client.post("/api/insight/query", json={"question": "我最近 10 天的体重趋势"})
        out = r.json()
        print("sql:", out.get("sql"))
        print("insight:", json.dumps(out.get("insight"), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--user", default="demo-001")
    args = parser.parse_args()
    asyncio.run(run(args.base_url, args.user))
