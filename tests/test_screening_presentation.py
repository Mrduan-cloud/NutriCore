"""NRS-2002 评分后**展示层**单测 —— BMI 标签、针对性建议、复评节奏、入口 quick replies。

scoring 算法本身的正确性由 test_nrs2002.py 守住,这里只测展示层把分析翻译成人话的部分。
都是纯函数,不需 DB / 网络。
"""
from app.agents.risk_screening.conversation import (
    _bmi_label,
    _completion_quick_replies,
    _next_screen_hint,
    _weak_spot_advice,
)

# ---------- 中国成人 BMI 分级(WS/T 428-2013)----------

def test_bmi_label_chinese_standard():
    assert _bmi_label(17.0) == "偏瘦"
    assert _bmi_label(18.5) == "正常"
    assert _bmi_label(23.9) == "正常"
    # 关键回归:历史 bug 把 25.47 标成"正常",中国标准应为"超重"
    assert _bmi_label(25.47) == "超重"
    assert _bmi_label(27.9) == "超重"
    assert _bmi_label(28.0) == "肥胖"


def test_bmi_label_does_not_lie_at_boundary():
    """20.5 是 NRS-2002 评分边界,但**标签**应该是"正常"——不能让评分逻辑污染人话标签。"""
    assert _bmi_label(20.5) == "正常"
    assert _bmi_label(22.0) == "正常"


# ---------- 复评节奏(NRS-2002 标准做法)----------

def test_next_screen_hint_by_total():
    # 有风险:1 周后(支持方案启动后)
    assert "1 周" in _next_screen_hint(3)
    assert "1 周" in _next_screen_hint(5)
    # 暂无风险但有扣分:1 周后复评(NRS-2002 标准)
    assert "1 周" in _next_screen_hint(1)
    assert "1 周" in _next_screen_hint(2)
    # 全 0 分:更长间隔
    assert "1 周" not in _next_screen_hint(0)
    assert "半年" in _next_screen_hint(0) or "复测" in _next_screen_hint(0)


# ---------- 针对性建议(按扣分维度,不空泛)----------

def test_advice_targets_intake_only_when_intake_loses_points():
    parts = {"intake": 1, "weight_loss": 0, "bmi": 0}
    slots = {"intake_band": "p50_75"}
    advice = _weak_spot_advice(parts, slots)
    assert len(advice) == 1
    assert "进食" in advice[0]
    # 不该泛泛而谈,需要有可执行建议
    assert "加餐" in advice[0]


def test_advice_no_deficit_returns_empty():
    """全 0 分时不出"针对性建议"小节,避免空泛凑数。"""
    assert _weak_spot_advice({"intake": 0, "weight_loss": 0, "bmi": 0}, {}) == []


def test_advice_covers_multiple_deficits():
    parts = {"intake": 2, "weight_loss": 1, "bmi": 3}
    slots = {"intake_band": "p25_50", "weight_loss_band": "1_5pct"}
    advice = _weak_spot_advice(parts, slots)
    assert len(advice) == 3
    joined = " ".join(advice)
    assert "进食" in joined and "体重" in joined and "BMI" in joined


# ---------- 评分后的 quick replies(让用户能"再点一步")----------

def test_quick_replies_no_risk():
    qr = _completion_quick_replies(0, {"intake": 0, "weight_loss": 0, "bmi": 0})
    assert any("保养" in q or "食谱" in q for q in qr)
    assert any("分数" in q for q in qr)


def test_quick_replies_score_1_2_includes_targeted_question():
    """1-2 分(进食扣分)→ 应该出现"如何提升进食量"这种针对性入口,而不只是"做方案"。"""
    qr = _completion_quick_replies(2, {"intake": 1, "weight_loss": 0, "bmi": 0})
    assert any("进食量" in q for q in qr)
    assert any("营养方案" in q for q in qr)


def test_quick_replies_high_risk_offers_clinical_path():
    qr = _completion_quick_replies(4, {"intake": 2, "weight_loss": 1, "bmi": 0})
    # 有风险时不该让用户漫无目的
    assert any("营养支持" in q or "营养方案" in q for q in qr)
    assert any("营养师" in q or "分数" in q for q in qr)
