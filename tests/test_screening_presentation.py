"""NRS-2002 评分后**展示层**单测 —— BMI 标签、针对性建议、复评节奏、入口 quick replies。

scoring 算法本身的正确性由 test_nrs2002.py 守住,这里只测展示层把分析翻译成人话的部分。
都是纯函数,不需 DB / 网络。
"""
from app.agents.risk_screening.conversation import (
    _ask,
    _bmi_label,
    _completion_quick_replies,
    _kg_threshold,
    _next_screen_hint,
    _personalized_weight_question,
    _weak_spot_advice,
    _weight_trend_hint,
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


# ---------- 用户友好选项(普通话 + 公斤)----------

def test_kg_threshold_from_profile_weight():
    """5% 公斤阈值,普通人能据此判断 vs 抽象的 ">5%"。"""
    assert _kg_threshold({"weight_kg": 77}) == 4   # 77 * 0.05 = 3.85 → 4
    assert _kg_threshold({"weight_kg": 60}) == 3   # 60 * 0.05 = 3.0 → 3
    assert _kg_threshold({"weight_kg": 100}) == 5
    # 数据缺失保护
    assert _kg_threshold({}) is None
    assert _kg_threshold({"weight_kg": 0}) is None
    assert _kg_threshold({"weight_kg": None}) is None


def test_personalized_weight_question_uses_kg_threshold():
    """有体重数据 → 选项里出现具体 kg(用户能判断),且保留 % 标记(LLM 能抽取)。"""
    pq = _personalized_weight_question({"weight_kg": 77})
    assert pq is not None
    # 题面里写明用户体重 + 5% 对应的具体 kg
    assert "77 kg" in pq["message"]
    assert "4 kg" in pq["message"]
    # 选项 4 个,每个都带 kg(普通话)+ % 标记(LLM 锚定)
    assert len(pq["quick_replies"]) == 4
    for r in pq["quick_replies"]:
        assert "kg" in r
    assert "<5%" in pq["quick_replies"][0]
    assert ">5%" in pq["quick_replies"][1]


def test_personalized_weight_question_none_without_weight():
    """没体重数据应返回 None,_ask 退回默认问法(不能强造 kg 数字误导用户)。"""
    assert _personalized_weight_question({}) is None
    assert _personalized_weight_question({"weight_kg": None}) is None


def test_ask_falls_back_to_default_when_no_profile_weight():
    """没体重也得能问问题,不能崩 — 退回 SLOT_QUESTIONS 默认选项。"""
    out = _ask("weight_loss_band", profile={})
    assert "quick_replies" in out
    assert len(out["quick_replies"]) == 4
    # 默认选项不带 kg
    assert all("kg" not in r for r in out["quick_replies"])


def test_intake_options_use_everyday_language():
    """胃口题应用"七八成饱 / 吃一半"这种日常语言,而不只是干瘪的百分比。"""
    out = _ask("intake_band")
    joined = " ".join(out["quick_replies"])
    assert "七八成饱" in joined
    assert "一半" in joined or "吃一半" in joined
    # 仍保留 % 标记供 LLM 抽取器锚定
    assert ">75%" in joined and "50-75%" in joined


# ---------- 体重趋势 hint 按实际 delta 动态措辞 ----------

def test_weight_trend_hint_basically_stable():
    """delta < 2% → "基本稳定"(原硬编码字符串改成数据驱动)。"""
    hint = _weight_trend_hint({"weight_kg": 77}, {"first": 78.4, "last": 77.2, "days": 9})
    assert "基本稳定" in hint
    assert "4 kg" in hint  # 公斤阈值也带上
    assert "77 kg" in hint


def test_weight_trend_hint_over_5pct_warns():
    """近期短窗已超 5% → 提示用户但注明这只是短窗、3 个月趋势请据实回答。"""
    hint = _weight_trend_hint({"weight_kg": 70}, {"first": 75.0, "last": 70.0, "days": 30})
    assert "已超过 5%" in hint or "5%" in hint
    assert "3 个月" in hint  # 提醒用户筛查看的是 3 个月窗口


def test_weight_trend_hint_handles_missing_data_gracefully():
    """无 trend 数据时返回空串,不能崩。"""
    assert _weight_trend_hint({"weight_kg": 77}, None) == ""
    assert _weight_trend_hint({}, None) == ""
