"""ECharts 配置项生成 + 数据解读（四段式）。"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.core.llm import chat_complete

# 青绿系调色板:饼/柱多色时统一观感(line 用前端默认主色,无需在此指定)
_PALETTE = ["#2F8B89", "#7FC8A9", "#5FB49C", "#9AD9C8", "#38918C", "#C9E8DF", "#1F6F6C"]

# 意图关键词 → 图表类型(对话里问"占比/对比/趋势/均衡"等会改变选图)
_PIE_KW = ("占比", "构成", "比例", "分布", "组成", "结构")
_BAR_KW = ("对比", "排名", "各", "分别", "最多", "最高", "最低", "每日", "每天", "哪天")
_RADAR_KW = ("均衡", "雷达", "全面", "各营养素", "营养结构", "营养画像", "整体营养")

# 每日推荐参考值(粗略基线,用于雷达「实际(日均) vs 推荐」对照;
# 真实产品应按个体 TDEE / 性别 / 体重计算,这里仅作演示基线)。
# key = daily_intake / vitals 的列名;value = (中文标签, 每日推荐值)
_NUTRIENT_TARGETS: dict[str, tuple[str, float]] = {
    "protein": ("蛋白质(g)", 60),
    "carb": ("碳水(g)", 250),
    "fat": ("脂肪(g)", 60),
    "water_ml": ("水(ml)", 1500),
    "kcal": ("热量(kcal)", 1800),
    "steps": ("步数", 8000),
    "sleep_hours": ("睡眠(h)", 7.5),
}


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


def build_radar_option(
    title: str, indicators: list[dict], actual: list[float], target: list[float]
) -> dict[str, Any]:
    """营养均衡雷达:实际(日均) vs 推荐,一张图看多维度是否达标。"""
    return {
        "color": _PALETTE,
        "title": {"text": title, "left": "center"},
        "tooltip": {},
        "legend": {"bottom": 0, "data": ["实际(日均)", "推荐"]},
        "radar": {"indicator": indicators, "radius": "62%", "center": ["50%", "54%"]},
        "series": [{
            "type": "radar",
            "data": [
                {"value": actual, "name": "实际(日均)", "areaStyle": {"opacity": 0.18}},
                {"value": target, "name": "推荐", "lineStyle": {"type": "dashed"}},
            ],
        }],
    }


_AGG_PREFIXES = ("avg_", "average_", "mean_", "sum_", "total_", "min_", "max_", "count_")

# 营养指标同义词(英文列名 / 中文别名 / 带聚合前缀都能命中)
_NUTRIENT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "protein": ("protein", "蛋白", "蛋白质"),
    "carb": ("carb", "carbs", "carbohydrate", "碳水", "碳水化合物"),
    "fat": ("fat", "脂肪"),
    "water_ml": ("water", "饮水", "水"),
    "kcal": ("kcal", "calorie", "calories", "热量", "卡路里", "能量"),
    "steps": ("step", "步数", "步"),
    "sleep_hours": ("sleep", "睡眠"),
}
_MACRO_KCAL = {"carb": 4, "protein": 4, "fat": 9}  # 每克热量,用于宏量营养素「热量占比」
_DATE_NAMES = ("date", "day", "ts", "month", "week", "日期", "时间", "周", "月")


def _numeric_keys(row: dict) -> list[str]:
    return [k for k, v in row.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _canon(col: str) -> str:
    """归一化列名:去掉 avg_/sum_/total_ 等聚合前缀,便于匹配。"""
    c = str(col).strip().lower()
    changed = True
    while changed:
        changed = False
        for p in _AGG_PREFIXES:
            if c.startswith(p):
                c, changed = c[len(p):], True
    return c


def _nutrient_of(col: str) -> str | None:
    """列名 → 已知营养指标 key(兼容 avg_ 前缀 + 中英文别名),无法识别返回 None。"""
    c = _canon(col)
    for key, syns in _NUTRIENT_SYNONYMS.items():
        if c == key or any(s in c for s in syns):
            return key
    return None


def _label(col: str) -> str:
    n = _nutrient_of(col)
    return _NUTRIENT_TARGETS[n][0] if n else str(col)


def _date_key(keys: list[str]) -> str | None:
    return next((k for k in keys if _canon(k) in _DATE_NAMES), None)


def _radar_from_rows(rows: list[dict], num_keys: list[str], title: str) -> dict[str, Any] | None:
    """≥3 个可识别营养指标 → 聚合日均做雷达(实际 vs 推荐);否则 None。"""
    cols = [k for k in num_keys if _nutrient_of(k)]
    if len(cols) < 3:
        return None
    indicators, actual, target = [], [], []
    for c in cols:
        name, tgt = _NUTRIENT_TARGETS[_nutrient_of(c)]
        vals = [r[c] for r in rows if isinstance(r.get(c), (int, float))]
        avg = round(sum(vals) / len(vals), 1) if vals else 0
        indicators.append({"name": name, "max": round(max(tgt, avg) * 1.4, 1)})
        actual.append(avg)
        target.append(tgt)
    return build_radar_option(title, indicators, actual, target)


def _macro_donut(rows: list[dict], num_keys: list[str], title: str) -> dict[str, Any] | None:
    """三大产能营养素(碳水/蛋白/脂肪)→ 按**克数**占比(同单位,部分占整体)。

    用克数(而非热量贡献)是为了与四段式解读文本一致(文本也按克数算占比),
    避免「图说 52%、文字说 63%」的矛盾;且不混入热量/水等异单位指标。
    """
    macro = [k for k in num_keys if _nutrient_of(k) in _MACRO_KCAL]
    if len(macro) < 2:
        return None
    names, values = [], []
    for c in macro:
        vals = [r[c] for r in rows if isinstance(r.get(c), (int, float))]
        if not vals:
            continue
        names.append(_label(c))
        values.append(round(sum(vals) / len(vals), 1))  # 日均克数
    return build_pie_option(title, names, values) if len(values) >= 2 else None


def build_charts(rows: list[dict], title: str) -> list[dict[str, Any]]:
    """产出**对该数据有意义**的多套可切换图,第一个为推荐默认。

    每项 = {"type": "line|bar|pie|radar", "label": 中文, "option": ECharts 配置}。
    规避混单位假占比:只有同单位 / 宏量营养素才出环形,多营养素出雷达。
    """
    if not rows:
        return []
    keys = list(rows[0].keys())
    num_keys = _numeric_keys(rows[0])
    if not num_keys:
        return []
    q = title or ""
    want_pie = any(k in q for k in _PIE_KW)
    want_bar = any(k in q for k in _BAR_KW)
    want_radar = any(k in q for k in _RADAR_KW)
    date_key = _date_key(keys)

    options: dict[str, dict] = {}
    radar = _radar_from_rows(rows, num_keys, title)
    if radar:
        options["radar"] = radar
    donut = _macro_donut(rows, num_keys, title)
    if donut:
        options["pie"] = donut

    if date_key:
        vk = next((k for k in num_keys if k != date_key), None)
        if vk is not None:
            rs = sorted(rows, key=lambda r: str(r[date_key]))
            x = [str(r[date_key]) for r in rs]
            y = [r[vk] for r in rs]
            options["line"] = build_line_option(title, x, y, _label(vk))
            options["bar"] = build_bar_option(title, x, y, _label(vk))
    elif len(rows) == 1 and len(num_keys) >= 2:
        options["bar"] = build_bar_option(
            title, [_label(k) for k in num_keys], [rows[0][k] for k in num_keys]
        )
        # 仅当不含(异单位的)营养指标时,才允许通用占比饼;营养指标已由雷达/宏量环形承接
        if not any(_nutrient_of(k) for k in num_keys):
            options.setdefault(
                "pie",
                build_pie_option(title, [str(k) for k in num_keys], [rows[0][k] for k in num_keys]),
            )
    else:
        vk = num_keys[0]
        lk = next((k for k in keys if k not in num_keys), keys[0])
        names = [str(r[lk]) for r in rows]
        vals = [r[vk] for r in rows]
        options["bar"] = build_bar_option(title, names, vals, _label(vk))
        options.setdefault("pie", build_pie_option(title, names, vals))  # 同单位分类可占比

    if not options:
        return []

    # 选默认:意图优先 → 形状兜底
    if want_radar and "radar" in options:
        default = "radar"
    elif want_pie and "pie" in options:
        default = "pie"
    elif want_bar and "bar" in options:
        default = "bar"
    elif date_key and "line" in options:
        default = "line"
    else:
        default = next(t for t in ("radar", "line", "bar", "pie") if t in options)

    labels = {"line": "折线", "bar": "柱状", "pie": "环形", "radar": "雷达"}
    order = [default] + [t for t in ("line", "bar", "pie", "radar") if t in options and t != default]
    return [{"type": t, "label": labels[t], "option": options[t]} for t in order]


def rows_to_chart(rows: list[dict], title: str) -> dict[str, Any]:
    """智能选图,返回推荐的那一张(向后兼容)。多图切换用 build_charts。"""
    charts = build_charts(rows, title)
    return charts[0]["option"] if charts else {"title": {"text": title}, "noData": True}


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
