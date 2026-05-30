"""Intent router 与 NRS-2002 筛查的衔接路由 — 关键回归。

历史 bug:`_screening_in_progress` 把"评分结果"消息也判为"进行中",导致用户
看完结果后任何提问(包括点 quick reply 入口)都被劫持回筛查节点,原样吐回结果。
本套件守住"已完成 → 后续提问交回正常意图分类"这条边界。
"""
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.nutritionist.nodes import _screening_in_progress


def _state_with_ai_msgs(*texts: str) -> dict:
    """构造一个最小 state:把若干 AI 消息按时间顺序塞进 messages。"""
    msgs = [AIMessage(content=t) for t in texts]
    return {"messages": msgs}


def test_in_progress_when_latest_ai_is_a_question():
    """筛查中的提问消息(还没出结果)→ 进行中。"""
    state = _state_with_ai_msgs(
        "**NRS-2002 营养风险筛查**\n\n近 1-3 个月体重有没有明显下降?",
    )
    assert _screening_in_progress(state) is True


def test_not_in_progress_after_result_message():
    """**关键回归**:评分结果消息之后,新提问不能再被当作筛查衔接。"""
    state = _state_with_ai_msgs(
        "**NRS-2002 营养风险筛查**\n\n近 1-3 个月体重有没有明显下降?",
        # ↓ 这条是结果,包含"NRS-2002 营养风险筛查"字样但也带"评分结果"
        "### NRS-2002 评分结果(确定性计算)\n\n"
        "**A. 营养状态受损:1 分**\n"
        "**总分:1 分 → 暂无营养风险**\n"
        "**下次复评:** 1 周后",
    )
    assert _screening_in_progress(state) is False


def test_not_in_progress_when_no_screening_keywords():
    """普通对话 → 不在筛查中。"""
    state = _state_with_ai_msgs("你好,有什么营养问题想问吗?")
    assert _screening_in_progress(state) is False


def test_not_in_progress_when_no_ai_messages_yet():
    """空对话 / 仅有用户消息 → 不在筛查中。"""
    state = {"messages": [HumanMessage(content="帮我做一次筛查")]}
    assert _screening_in_progress(state) is False


def test_looks_at_latest_ai_only_not_history():
    """只看**最近一条** AI 消息;不能因为历史上做过筛查就一直返回 True。"""
    state = _state_with_ai_msgs(
        "**NRS-2002 营养风险筛查**\n\n近 1-3 个月体重?",
        "### NRS-2002 评分结果(确定性计算)\n**总分:1 分**\n**下次复评:** 1 周后",
        # 之后用户问其它问题、AI 回的不是筛查相关内容
        "鸡胸肉是常见的高蛋白低脂食材,每 100g 含蛋白质约 23g。",
    )
    assert _screening_in_progress(state) is False
