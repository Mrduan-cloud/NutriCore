"""数据洞察对外入口 — 优先调 Dify Workflow，未配置时本地走 NL2SQL + ECharts 兜底。

这样在未部署 Dify 的环境（CI / 本地 / 离线私有化）整条链路依然能跑通。
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from app.agents.data_insight.echarts import build_charts, four_paragraph_insight
from app.agents.data_insight.nl2sql import nl2sql
from app.config import get_settings


async def _dify_run(question: str, user_id: str) -> dict:
    s = get_settings()
    payload = {
        "inputs": {"question": question, "user_id": user_id},
        "response_mode": "blocking",
        "user": user_id,
    }
    headers = {"Authorization": f"Bearer {s.dify_api_key}"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{s.dify_api_base}/workflows/run", json=payload, headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def _local_fallback(question: str, user_id: str) -> dict[str, Any]:
    nl = await nl2sql(question, user_id)
    rows = nl["rows"]
    charts = build_charts(rows, title=question)  # 多套可切换图(推荐在首)
    insight = await four_paragraph_insight(rows, metric=question)
    return {
        "sql": nl["sql"],
        "rows": rows,
        "echarts_option": charts[0]["option"] if charts else {"noData": True},
        "echarts_charts": charts,
        "insight": insight,
        "source": "local",
    }


async def run_workflow(question: str, user_id: str) -> dict[str, Any]:
    s = get_settings()
    if s.dify_api_key:
        try:
            data = await _dify_run(question, user_id)
            data["source"] = "dify"
            return data
        except Exception as e:
            logger.warning("dify failed, fallback to local: {}", e)
    return await _local_fallback(question, user_id)