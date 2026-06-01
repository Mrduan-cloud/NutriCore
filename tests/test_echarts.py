"""数据洞察智能选图单测 —— 按问题意图 + 数据形状选 折线/柱/饼。"""
from app.agents.data_insight.echarts import rows_to_chart


def _type(chart: dict) -> str:
    return (chart.get("series") or [{}])[0].get("type")


def test_time_series_defaults_to_line():
    rows = [{"date": "2026-05-01", "protein": 80}, {"date": "2026-05-02", "protein": 82}]
    assert _type(rows_to_chart(rows, "近30天蛋白质趋势")) == "line"


def test_time_series_with_compare_keyword_is_bar():
    rows = [{"date": "2026-05-01", "steps": 8000}, {"date": "2026-05-02", "steps": 9000}]
    assert _type(rows_to_chart(rows, "近一周每日步数对比")) == "bar"


def test_single_row_multi_metric_is_pie():
    rows = [{"碳水": 260, "蛋白质": 80, "脂肪": 65}]
    assert _type(rows_to_chart(rows, "三大产能营养素占比")) == "pie"


def test_single_row_multi_metric_with_bar_keyword():
    rows = [{"碳水": 260, "蛋白质": 80, "脂肪": 65}]
    assert _type(rows_to_chart(rows, "三大营养素各是多少")) == "bar"


def test_categorical_defaults_to_bar():
    rows = [{"meal": "早餐", "kcal": 500}, {"meal": "午餐", "kcal": 700}]
    assert _type(rows_to_chart(rows, "每餐热量")) == "bar"


def test_categorical_with_pie_keyword():
    rows = [{"meal": "早餐", "kcal": 500}, {"meal": "午餐", "kcal": 700}]
    assert _type(rows_to_chart(rows, "每餐热量占比")) == "pie"


def test_pie_value_alignment():
    chart = rows_to_chart([{"a": 1, "b": 2, "c": 3}], "占比")
    data = chart["series"][0]["data"]
    assert [d["name"] for d in data] == ["a", "b", "c"]
    assert [d["value"] for d in data] == [1, 2, 3]


def test_balance_question_with_multi_nutrient_is_radar():
    rows = [
        {"date": "2026-05-01", "protein": 80, "carb": 260, "fat": 65, "water_ml": 1900},
        {"date": "2026-05-02", "protein": 78, "carb": 250, "fat": 62, "water_ml": 1800},
    ]
    chart = rows_to_chart(rows, "我最近的营养摄入均衡吗")
    assert _type(chart) == "radar"
    # 实际(日均) + 推荐 两条
    assert len(chart["series"][0]["data"]) == 2
    assert {d["name"] for d in chart["series"][0]["data"]} == {"实际(日均)", "推荐"}


def test_balance_question_without_enough_nutrients_falls_back():
    # 只有 1 个营养指标(<3)→ 不出雷达,退回时间序列折线
    rows = [{"date": "2026-05-01", "protein": 80}, {"date": "2026-05-02", "protein": 78}]
    assert _type(rows_to_chart(rows, "蛋白质均衡吗")) == "line"


def test_empty_rows_returns_no_data():
    assert rows_to_chart([], "x").get("noData") is True


def test_rows_without_numeric_returns_no_data():
    assert rows_to_chart([{"label": "x"}], "y").get("noData") is True


# ---- 回归:NL2SQL 的 avg_ 前缀列名 + 不能混单位假占比 ----

def test_avg_prefixed_nutrients_trigger_radar():
    """avg_protein 等聚合前缀列名也要能识别 → 营养均衡出雷达,而非乱算占比。"""
    rows = [{"avg_kcal": 2004, "avg_protein": 80, "avg_carb": 252, "avg_fat": 65, "avg_water_ml": 1861}]
    assert _type(rows_to_chart(rows, "我的营养摄入均衡吗")) == "radar"


def test_mixed_unit_nutrients_never_become_pie():
    """热量+水+蛋白质 单位不同,绝不能出占比饼(截图里的 bug)。"""
    rows = [{"avg_kcal": 2004, "avg_protein": 80, "avg_water_ml": 1861}]
    from app.agents.data_insight.echarts import build_charts
    types = {c["type"] for c in build_charts(rows, "营养均衡")}
    # 可以有雷达/柱,但不能把异单位指标做成饼
    assert "pie" not in types


def test_macro_composition_pie_by_energy():
    """三大产能营养素占比 → 按供能比(热量):碳水/蛋白 ×4、脂肪 ×9 kcal/g。"""
    rows = [{"avg_carb": 100, "avg_protein": 100, "avg_fat": 100}]
    chart = rows_to_chart(rows, "三大产能营养素占比")
    assert _type(chart) == "pie"
    vals = {d["name"]: d["value"] for d in chart["series"][0]["data"]}
    assert vals["碳水"] == 400  # 100g × 4
    assert vals["蛋白质"] == 400  # 100g × 4
    assert vals["脂肪"] == 900  # 100g × 9


def test_build_charts_offers_alternatives():
    """时间序列应同时提供 折线 + 柱 供切换,推荐项在首。"""
    from app.agents.data_insight.echarts import build_charts
    rows = [{"date": "2026-05-01", "protein": 80}, {"date": "2026-05-02", "protein": 82}]
    charts = build_charts(rows, "近30天蛋白质趋势")
    assert charts[0]["type"] == "line"
    assert {c["type"] for c in charts} >= {"line", "bar"}


# ---- 「达标」时序图必须画出推荐参考线(否则用户看不懂达标没达标) ----

def test_nutrient_timeseries_has_target_markline():
    """蛋白质达标折线:应有推荐 60g 的 markLine,且摄入型指标加「达标区」绿带。"""
    rows = [{"date": "2026-05-01", "protein": 80}, {"date": "2026-05-02", "protein": 82}]
    chart = rows_to_chart(rows, "近30天蛋白质达标情况")
    series = chart["series"][0]
    assert "markLine" in series, "达标图必须有推荐参考线"
    assert series["markLine"]["data"][0]["yAxis"] == 60  # protein 推荐 60g
    assert "≥" in series["markLine"]["label"]["formatter"]  # 越多越好 → 用「推荐 ≥」
    assert "markArea" in series, "摄入越多越好的指标应有达标区绿带"


def test_range_nutrient_has_line_but_no_goal_band():
    """脂肪是范围型(过多也不好):给参考线,但不染「达标区」绿带。"""
    rows = [{"date": "2026-05-01", "fat": 50}, {"date": "2026-05-02", "fat": 55}]
    chart = rows_to_chart(rows, "近一周脂肪趋势")
    series = chart["series"][0]
    assert "markLine" in series
    assert "markArea" not in series  # 范围型不染达标区
    assert "≥" not in series["markLine"]["label"]["formatter"]  # 用「推荐 」不带 ≥


def test_unknown_metric_no_markline():
    """非已知营养指标(无推荐基线)→ 不强加参考线。"""
    rows = [{"date": "2026-05-01", "mystery": 5}, {"date": "2026-05-02", "mystery": 7}]
    chart = rows_to_chart(rows, "近一周趋势")
    assert "markLine" not in chart["series"][0]
