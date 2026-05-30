"""ECharts 配置项生成 + 数据解读（四段式）。"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.core.llm import chat_complete


def build_line_option(title: str, x: list, y: list, y_label: str = "") -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 50, "right": 30, "top": 60, "bottom": 40},
        "xAxis": {"type": "category", "data": x},
        "yAxis": {"type": "value", "name": y_label},
        "series": [{
            "type": "line", "data": y, "smooth": True,
            "areaStyle": {"opacity": 0.15},
            "lineStyle": {"width": 2},
        }],
    }


def rows_to_chart(rows: list[dict], title: str) -> dict[str, Any]:
    """将单序列查询结果转为 ECharts 配置 — 自动识别 date + 第一数值列。"""
    if not rows:
        return {"title": {"text": title}, "noData": True}
    keys = list(rows[0].keys())
    date_key = next((k for k in keys if k.lower() in ("date", "day", "ts")), keys[0])
    value_key = next((k for k in keys if k != date_key and isinstance(rows[0][k], (int, float))), None)
    if value_key is None:
        return {"title": {"text": title}, "noData": True}
    rows_sorted = sorted(rows, key=lambda r: str(r[date_key]))
    x = [str(r[date_key]) for r in rows_sorted]
    y = [r[value_key] for r in rows_sorted]
    return build_line_option(title, x, y, value_key)


_INSIGHT_PROMPT = """你是健康数据解读师。基于以下时序数据，输出严格 JSON：
{{
  "overview": "数据概况（1-2 句）",
  "findings": "关键发现（1-3 条要点）",
  "alerts": "异常预警（若无写'暂无明显异常'）",
  "actions": "行动建议（具体、可执行）"
}}
数据指标：{metric}
数据 (最多 30 行)：{rows}

只输出 JSON。"""


async def four_paragraph_insight(rows: list[dict], metric: str) -> dict[str, str]:
    if not rows:
        return {
            "overview": "该时段无数据",
            "findings": "暂无数据，无法分析",
            "alerts": "无",
            "actions": "建议先开启每日记录习惯",
        }
    try:
        raw = await chat_complete(
            _INSIGHT_PROMPT.format(metric=metric, rows=json.dumps(rows[:30], ensure_ascii=False, default=str)),
            response_format="json",
            temperature=0.2,
            max_tokens=600,
        )
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        logger.warning("insight generation failed: {}", e)
    return {
        "overview": f"{metric} 共 {len(rows)} 条记录",
        "findings": "数据呈一定波动",
        "alerts": "暂无明显异常",
        "actions": "建议保持记录，下次复盘前再积累 2 周数据",
    }
