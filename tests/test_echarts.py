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
