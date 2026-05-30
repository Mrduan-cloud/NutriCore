"""ECharts 配置项生成 + 数据解读（四段式）。"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.core.llm import chat_complete


# 青绿系调色板:饼/柱多色时统一观感(line 用前端默认主色,无需在此指定)
_PALETTE = ["#2F8B89", "#7FC8A9", "#5FB49C", "#9AD9C8", "#38918C", "#C9E8DF", "#1F6F6C"]

# 意图关键词 → 图表类型(对话里问"占比/对比/趋势"等会改变选图)
_PIE_KW = ("占比", "构成", "比例", "分布", "组成", "结构")
_BAR_KW = ("对比", "排名", "各", "分别", "最多", "最高", "最低", "每日", "每天", "哪天")


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


def build_bar_option(title: str, x: list, y: list, y_label: str = "") -> dict[str, Any]:
    return {
        "color": _PALETTE,
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 50, "right": 30, "top": 60, "bottom": 40},
        "xAxis": {"type": "category", "data": x},
        "yAxis": {"type": "value", "name": y_label},
        "series": [{
            "type": "bar", "data": y, "barWidth": "48%",
            "itemStyle": {"borderRadius": [6, 6, 0, 0]},
        }],
    }


def build_pie_option(title: str, names: list, values: list) -> dict[str, Any]:
    data = [{"name": str(n), "value": v} for n, v in zip(names, values, strict=True)]
    return {
        "color": _PALETTE,
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"bottom": 0, "left": "center"},
        "series": [{
            "type": "pie", "radius": ["42%", "68%"], "center": ["50%", "46%"],
            "avoidLabelOverlap": True,
            "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
            "label": {"formatter": "{b}\n{d}%"},
            "data": data,
        }],
    }


def _numeric_keys(row: dict) -> list[str]:
    return [k for k, v in row.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def rows_to_chart(rows: list[dict], title: str) -> dict[str, Any]:
    """把查询结果转为 ECharts 配置,**按问题意图 + 数据形状智能选图**:

    - 单行多指标(如 平均碳水/蛋白质/脂肪)→ 饼图(占比)/ 柱图
    - 时间序列(含日期列)→ 折线(趋势,默认)/ 柱图(问"对比/每日"时)
    - 分类(标签列 + 数值列)→ 柱图 / 饼图(问"占比"时)
    """
    if not rows:
        return {"title": {"text": title}, "noData": True}
    keys = list(rows[0].keys())
    num_keys = _numeric_keys(rows[0])
    if not num_keys:
        return {"title": {"text": title}, "noData": True}
    q = title or ""
    want_pie = any(k in q for k in _PIE_KW)
    want_bar = any(k in q for k in _BAR_KW)

    # 形态 1:单行多指标 → 饼(默认,适合"占比/构成")或柱
    if len(rows) == 1 and len(num_keys) >= 2:
        values = [rows[0][k] for k in num_keys]
        return build_bar_option(title, num_keys, values) if want_bar \
            else build_pie_option(title, num_keys, values)

    # 形态 2:时间序列 → 折线(默认)/柱
    date_key = next(
        (k for k in keys if k.lower() in ("date", "day", "ts", "month", "week")), None
    )
    if date_key:
        value_key = next((k for k in num_keys if k != date_key), None)
        if value_key is None:
            return {"title": {"text": title}, "noData": True}
        rs = sorted(rows, key=lambda r: str(r[date_key]))
        x = [str(r[date_key]) for r in rs]
        y = [r[value_key] for r in rs]
        return build_bar_option(title, x, y, value_key) if want_bar \
            else build_line_option(title, x, y, value_key)

    # 形态 3:分类(标签 + 数值)→ 柱(默认)/饼
    value_key = num_keys[0]
    label_key = next((k for k in keys if k not in num_keys), keys[0])
    names = [str(r[label_key]) for r in rows]
    values = [r[value_key] for r in rows]
    return build_pie_option(title, names, values) if want_pie \
        else build_bar_option(title, names, values, value_key)


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
