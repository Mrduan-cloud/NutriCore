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


def test_empty_rows_returns_no_data():
    assert rows_to_chart([], "x").get("noData") is True


def test_rows_without_numeric_returns_no_data():
    assert rows_to_chart([{"label": "x"}], "y").get("noData") is True
