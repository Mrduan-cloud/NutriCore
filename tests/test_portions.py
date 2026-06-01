"""家常量词换算单测 —— 让膳食方案的"克"变成"几个/几碗/几掌心"。"""
from app.agents.meal_plan.portions import portion_hint, uses_hand_estimate


def test_discrete_items_count():
    assert portion_hint("鸡蛋", 50) == "1个"
    assert portion_hint("鸡蛋", 100) == "2个"
    assert portion_hint("苹果", 200) == "1个"
    assert portion_hint("香蕉", 130) == "1根"


def test_staple_in_bowls():
    assert portion_hint("糙米饭", 150) == "1碗"
    assert portion_hint("米饭", 300) == "2碗"


def test_hand_rule_protein_and_veg():
    assert portion_hint("鸡胸肉", 100) == "1掌心"
    assert portion_hint("三文鱼", 100) == "1掌心"
    assert portion_hint("西兰花", 200) == "2拳"
    assert portion_hint("烹调油", 10) == "1瓷勺"


def test_rounds_to_half_unit():
    # 全麦面包 1 片≈35g → 60g 约 1.5 片(取到 0.5,不出现 1.71 片)
    assert portion_hint("全麦面包", 60) == "1.5片"
    # 不足半份也至少给"半",避免出现"0个"
    assert portion_hint("鸡蛋", 10) == "半个"


def test_fuzzy_name_contains_match():
    # 带修饰词也能命中(取最长键更精确)
    assert portion_hint("水煮西兰花", 100) == "1拳"
    assert portion_hint("清蒸三文鱼", 100) == "1掌心"


def test_unknown_food_returns_empty():
    assert portion_hint("海参", 50) == ""
    assert portion_hint("鸡蛋", None) == ""
    assert portion_hint("", 50) == ""


def test_uses_hand_estimate_flag():
    # 掌心/拳/瓷勺 属手掌法则 → 需要附说明
    assert uses_hand_estimate("鸡胸肉") is True
    assert uses_hand_estimate("西兰花") is True
    assert uses_hand_estimate("烹调油") is True
    # 个/碗/根/片 是直观量词 → 不需要
    assert uses_hand_estimate("鸡蛋") is False
    assert uses_hand_estimate("糙米饭") is False
    assert uses_hand_estimate("未知食材") is False
