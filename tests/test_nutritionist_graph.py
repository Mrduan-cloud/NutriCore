"""主控 LangGraph 子图 happy path 测试 —— 简历"AI 营养师 Agent · LangGraph 多 Agent 编排"段落背书。

覆盖范围:
1. 拓扑层 — build 不抛 / 6 节点齐全
2. 路由层 — 高风险关键词 → safety_fallback / 4 意图 → 对应子 Agent
3. 容错层 — LLM 异常 / 实体抽取失败,链路仍能跑完
4. 节点单测 — citation_validator / memory_node 的独立行为

所有外部依赖(LLM / 子 Agent 业务函数 / Dify HTTP)都被 monkeypatch,
单测**完全离线、确定性**,可以在 CI 任意环境跑。
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from app.agents.nutritionist import nodes
from app.agents.nutritionist.graph import _route, build_nutritionist_graph


# =========================================================================
# Fixtures — 把所有 LLM / 子 Agent 调用都换成确定性桩
# =========================================================================
@pytest.fixture
def patch_chat_complete(monkeypatch):
    """工厂:返回一个 patcher,调用它就替换 chat_complete 的两个使用点。

    用法:
        async def stub(_prompt, **_): return '{"intent": "plan"}'
        patch_chat_complete(stub)
    """

    def _apply(stub):
        # intent_router / general_consult 用的是 nodes 模块里的 chat_complete
        monkeypatch.setattr(nodes, "chat_complete", stub, raising=True)
        # memory_node → extract_entities 用的是 memory 模块里的 chat_complete
        from app.agents.nutritionist import memory as memory_mod

        monkeypatch.setattr(memory_mod, "chat_complete", stub, raising=True)
        # 风险筛查 screen_step 的槽位抽取走 risk_screening.conversation 的 chat_complete
        from app.agents.risk_screening import conversation as screening_conv

        monkeypatch.setattr(screening_conv, "chat_complete", stub, raising=True)

    return _apply


@pytest.fixture
def patch_meal_plan(monkeypatch):
    """替换 generate_meal_plan,避免触发真实 LLM + Milvus + 校验链。"""

    def _apply(stub):
        # subagent_dispatcher 里是 lazy import 'from app.agents.meal_plan.generator import generate_meal_plan'
        # 直接替换源模块的属性,lazy import 拿到的就是替换后的版本
        from app.agents.meal_plan import generator as gen_mod

        monkeypatch.setattr(gen_mod, "generate_meal_plan", stub, raising=True)

    return _apply


@pytest.fixture
def patch_dify_workflow(monkeypatch):
    """替换 run_workflow,避免触发真实 Dify HTTP / NL2SQL 兜底。"""

    def _apply(stub):
        from app.agents.data_insight import dify_client

        monkeypatch.setattr(dify_client, "run_workflow", stub, raising=True)

    return _apply


@pytest.fixture(autouse=True)
def offline_consult(monkeypatch):
    """默认把 consult 的 RAG 检索打成空 —— 让整套图测试**完全离线**,
    不连 Milvus / 不加载 reranker 模型。需要真实检索的测试可自行覆盖。
    """

    async def _no_rag(query, top_k=3):
        return "", []

    monkeypatch.setattr(nodes, "consult_rag_context", _no_rag, raising=True)


@pytest.fixture
def patch_consult(monkeypatch):
    """按需让 consult RAG 返回指定证据 + 引用(覆盖 autouse 的空实现)。"""

    def _apply(evidence: str = "", citations: list | None = None):
        async def _stub(query, top_k=3):
            return evidence, list(citations or [])

        monkeypatch.setattr(nodes, "consult_rag_context", _stub, raising=True)

    return _apply


def _make_state(text: str, **extra: Any) -> dict:
    base = {
        "messages": [HumanMessage(content=text)],
        "user_id": "u-test",
        "user_profile": {},
    }
    base.update(extra)
    return base


# =========================================================================
# 拓扑层
# =========================================================================
def test_build_nutritionist_graph_does_not_raise():
    g = build_nutritionist_graph()
    assert g is not None
    assert hasattr(g, "ainvoke")


def test_graph_has_all_seven_nodes():
    """7 节点齐全 —— 拓扑契约。改动节点数应该让测试爆掉,防意外删除。"""
    g = build_nutritionist_graph()
    # LangGraph CompiledStateGraph 把节点放在 .get_graph() 里
    expected = {
        "memory",
        "intent_router",
        "subagent_dispatcher",
        "tool_executor",
        "citation_validator",
        "safety_fallback",
        "general_consult",  # consult 意图的真实作答节点
    }
    actual = set(g.get_graph().nodes.keys())
    # 'start' / '__start__' 等内部节点不进 expected,只要包含 expected 即可
    missing = expected - actual
    assert not missing, f"缺失节点: {missing} (实际: {actual})"


def test_route_helper_handles_three_branches():
    """_route 是路由分支的核心,单独验证三种状态。"""
    assert _route({"is_high_risk": True}) == "high_risk"
    assert _route({"selected_subagent": "meal_plan"}) == "subagent"
    # 无子 Agent 且非高风险 = 一般咨询 → general_consult(此前是直接 END)
    assert _route({}) == "consult"
    # is_high_risk 优先级最高 —— 即使有 selected_subagent 也要先兜底
    assert _route({"is_high_risk": True, "selected_subagent": "meal_plan"}) == "high_risk"


# =========================================================================
# 路由层 — 高风险关键词短路
# =========================================================================
@pytest.mark.asyncio
async def test_high_risk_keyword_short_circuits_to_safety_fallback(patch_chat_complete):
    """胸痛 / 急救 / 孕期 等关键词 → 直接走 safety_fallback,不调 LLM 也不调子 Agent。"""

    async def _llm_should_not_be_called(_prompt, **_):
        raise AssertionError("高风险关键词命中时 intent LLM 不应被调用")

    patch_chat_complete(_llm_should_not_be_called)
    g = build_nutritionist_graph()

    final = await g.ainvoke(_make_state("胸痛厉害,该吃什么"))

    assert final.get("is_high_risk") is True
    assert final["intent"] == "risk_alert"
    assert final.get("selected_subagent") is None
    # safety_fallback 文案导向"前往正规医院 / 专科医生"
    assert "医院" in final["final_answer"] or "就医" in final["final_answer"]


@pytest.mark.asyncio
async def test_high_risk_keyword_works_with_multimodal_content(patch_chat_complete):
    """LangChain 0.3+ 多模态消息(content=list[dict])下高风险 gate 仍要命中。

    回归测试 —— 防止 ``_last_user_text`` 把 list 透传给 ``"急救" in text``
    检查导致 gate 被静默绕过(那种情况下 ``"急救" in [{...}, {...}]`` 永远
    返回 False,简历声明的"高风险问题自动触发建议就医"会失效)。
    """

    async def _llm_should_not_be_called(_prompt, **_):
        raise AssertionError("多模态消息携带的高风险关键词应在规则层就被截下")

    patch_chat_complete(_llm_should_not_be_called)
    g = build_nutritionist_graph()

    state = {
        "messages": [HumanMessage(content=[
            {"type": "text", "text": "胸痛厉害,该吃什么"},
            {"type": "image_url", "image_url": {"url": "fake.jpg"}},
        ])],
        "user_id": "u-mm",
        "user_profile": {},
    }
    final = await g.ainvoke(state)

    assert final.get("is_high_risk") is True
    assert final["intent"] == "risk_alert"
    # safety_fallback 实际文案使用"建议尽快前往专科医院",与上面 ASCII-safe gate 测试保持一致
    assert "急" in final["final_answer"] or "医院" in final["final_answer"]


# =========================================================================
# 路由层 — 4 个意图分支
# =========================================================================
@pytest.mark.asyncio
async def test_consult_intent_answers_via_general_consult(patch_chat_complete, patch_consult):
    """consult 意图 → 无子 Agent → general_consult 用 RAG 接地作答(不再直接 END)。

    LLM 返回非 JSON 的自然语言 → intent 默认 consult;general_consult 用同一
    chat_complete 产出最终答复。RAG 用 patch_consult 打成空 → 离线 + 无引用。
    """

    async def _stub(_prompt, **_):
        return "建议优先选全谷物等低 GI 主食,搭配蔬菜与优质蛋白。"

    patch_chat_complete(_stub)
    patch_consult(evidence="", citations=[])  # 知识库无匹配 → 无引用
    g = build_nutritionist_graph()

    final = await g.ainvoke(_make_state("低 GI 主食有哪些?"))

    assert final["intent"] == "consult"
    assert final.get("selected_subagent") is None
    # general_consult 产出了真实答复
    assert "全谷物" in final["final_answer"]
    # 知识库无匹配 → citations 为空(诚实溯源)
    assert final.get("citations") == []


@pytest.mark.asyncio
async def test_consult_attaches_citations_when_kb_matches(patch_chat_complete, patch_consult):
    """consult 命中知识库时,general_consult 应回传真实引用。"""

    async def _stub(_prompt, **_):
        return "膳食指南建议每日全谷物 50-150g。"

    patch_chat_complete(_stub)
    patch_consult(evidence="[dietary_guide:c1] 全谷物...", citations=["dietary_guide:c1"])
    g = build_nutritionist_graph()

    final = await g.ainvoke(_make_state("每天该吃多少全谷物?"))

    assert final["intent"] == "consult"
    assert "dietary_guide:c1" in final["citations"]


@pytest.mark.asyncio
async def test_screening_intent_routes_to_dispatcher(patch_chat_complete):
    async def _stub(_prompt, **_):
        return '{"intent": "screening"}'

    patch_chat_complete(_stub)
    g = build_nutritionist_graph()

    final = await g.ainvoke(_make_state("帮我做营养风险评估"))

    assert final["intent"] == "screening"
    assert final["selected_subagent"] == "risk_screening"
    assert "营养风险筛查" in final["final_answer"] or "NRS" in final["final_answer"]
    # 工具名已从 risk_screening_intro 改为确定性评分链路 nrs2002_screening
    assert any(c.get("tool") == "nrs2002_screening" for c in final.get("tool_calls", []))


@pytest.mark.asyncio
async def test_plan_intent_invokes_meal_plan_generator(
    patch_chat_complete, patch_meal_plan
):
    """plan 意图 → 调 generate_meal_plan,把返回的 citations 收集进 state。"""

    async def _llm_stub(prompt, **_):
        # 任何 chat_complete 都返回 plan 意图;extract_entities 因为消息长度 < 4 短路掉
        return '{"intent": "plan"}'

    fake_plan = {
        "days": [
            {
                "breakfast": [{"name": "燕麦", "citations": ["dietary_guide:c1"]}],
                "lunch": [{"name": "鸡胸肉", "citations": ["food_comp:c2"]}],
                "dinner": [],
                "snack": [],
            }
        ]
    }

    async def _meal_plan_stub(_profile, user_request, **_):
        return fake_plan

    patch_chat_complete(_llm_stub)
    patch_meal_plan(_meal_plan_stub)

    g = build_nutritionist_graph()
    final = await g.ainvoke(_make_state("生成一份 7 天减脂方案"))

    assert final["intent"] == "plan"
    assert final["selected_subagent"] == "meal_plan"
    assert "方案" in final["final_answer"]
    # 引用应该被 citation_validator 过过滤但保留(都含":")
    assert "dietary_guide:c1" in final["citations"]
    assert "food_comp:c2" in final["citations"]


@pytest.mark.asyncio
async def test_insight_intent_invokes_dify_workflow(
    patch_chat_complete, patch_dify_workflow
):
    async def _llm_stub(_prompt, **_):
        return '{"intent": "insight"}'

    called = {}

    async def _workflow_stub(question: str, user_id: str):
        called["question"] = question
        called["user_id"] = user_id
        return {"chart": {"type": "line"}, "summary": "近 30 天蛋白质达标率 78%"}

    patch_chat_complete(_llm_stub)
    patch_dify_workflow(_workflow_stub)

    g = build_nutritionist_graph()
    final = await g.ainvoke(
        _make_state("我最近 30 天蛋白质达标了吗", user_id="u-42")
    )

    assert final["intent"] == "insight"
    assert final["selected_subagent"] == "data_insight"
    assert "数据洞察" in final["final_answer"] or "可视化" in final["final_answer"]
    assert called["user_id"] == "u-42"
    assert "extra" in final and "insight" in final["extra"]


# =========================================================================
# 容错层 — LLM 异常时仍要跑完
# =========================================================================
@pytest.mark.asyncio
async def test_intent_llm_failure_falls_back_to_consult(patch_chat_complete):
    """intent LLM 抛错 → intent_router 应捕获 → 默认 consult,链路不崩。"""

    async def _boom(_prompt, **_):
        raise RuntimeError("vLLM unreachable")

    patch_chat_complete(_boom)
    g = build_nutritionist_graph()

    final = await g.ainvoke(_make_state("吃啥好?"))
    assert final["intent"] == "consult"
    assert final.get("selected_subagent") is None
    assert final.get("is_high_risk") is False


@pytest.mark.asyncio
async def test_intent_llm_returns_invalid_json_falls_back_to_consult(patch_chat_complete):
    """LLM 返回非 JSON / 没有 intent 字段 → 默认 consult。"""

    async def _bad(_prompt, **_):
        return "我看你想要…什么呢"  # 不是 JSON

    patch_chat_complete(_bad)
    g = build_nutritionist_graph()
    final = await g.ainvoke(_make_state("balabala"))
    assert final["intent"] == "consult"


# =========================================================================
# 节点单测 — 独立验证 citation_validator / memory_node
# =========================================================================
@pytest.mark.asyncio
async def test_citation_validator_filters_malformed_entries():
    state = {
        "citations": [
            "dietary_guide:c1",         # 保留
            "food_comp:42",             # 保留
            "no_colon_here",            # 丢
            123,                         # 丢 (非 str)
            None,                        # 丢
            "another:valid",            # 保留
        ]
    }
    out = await nodes.citation_validator(state)
    assert out["citations"] == ["dietary_guide:c1", "food_comp:42", "another:valid"]


@pytest.mark.asyncio
async def test_citation_validator_handles_missing_citations_key():
    """state 里完全没有 citations 字段时,返回空列表而不是 KeyError。"""
    out = await nodes.citation_validator({})
    assert out["citations"] == []


@pytest.mark.asyncio
async def test_memory_node_merges_extracted_fields_into_profile(monkeypatch):
    """memory_node:从 LLM 抽取的字段应该合入既有画像,list 字段做 union。"""

    async def _fake_chat(_prompt, **_):
        return '{"age": 30, "weight_kg": 70, "height_cm": 175, "allergies": ["花生"]}'

    from app.agents.nutritionist import memory as memory_mod

    monkeypatch.setattr(memory_mod, "chat_complete", _fake_chat, raising=True)

    state = {
        "messages": [HumanMessage(content="我 30 岁,身高 175,体重 70,对花生过敏")],
        "user_id": "u-9",
        "user_profile": {"chronic_diseases": ["高血压"], "allergies": ["海鲜"]},
    }
    out = await nodes.memory_node(state)
    profile = out["user_profile"]

    assert profile["age"] == 30
    assert profile["weight_kg"] == 70
    assert profile["height_cm"] == 175
    # list 字段:并集,不应覆盖
    assert set(profile["allergies"]) == {"花生", "海鲜"}
    assert profile["chronic_diseases"] == ["高血压"]
    # BMI 应该被自动计算
    assert profile["bmi"] == pytest.approx(70 / (1.75**2), rel=1e-2)


@pytest.mark.asyncio
async def test_memory_node_handles_empty_message_gracefully(monkeypatch):
    """消息太短 (<4 字符) → extract_entities 短路返回 {} → memory_node 不改 profile。"""

    async def _should_not_call(*_, **__):
        raise AssertionError("短消息不应该触发 LLM 调用")

    from app.agents.nutritionist import memory as memory_mod

    monkeypatch.setattr(memory_mod, "chat_complete", _should_not_call, raising=True)

    state = {
        "messages": [HumanMessage(content="嗨")],
        "user_id": "u-9",
        "user_profile": {"age": 28},
    }
    out = await nodes.memory_node(state)
    # 节点契约要求至少回写一个 schema 字段(LangGraph 不允许空 patch),
    # 因此短路时回写原 profile 作为 noop —— 内容不应被改动
    assert out == {"user_profile": {"age": 28}}


# =========================================================================
# 安全层 — 防 LLM 输出污染 / 内部细节泄漏
# =========================================================================
@pytest.mark.asyncio
async def test_malicious_llm_intent_is_coerced_to_whitelist(patch_chat_complete):
    """LLM 返回不在白名单的 intent(可能是注入攻击 / 模型漂移)→ 必须被收敛为 consult。

    防御:
    - state["intent"] 后续用于审计/前端渲染,不能直接写 LLM 输出
    - Prometheus label cardinality(防 series 爆炸 OOM)
    """

    async def _malicious_llm(_prompt, **_):
        # 模拟恶意/异常的 LLM 输出
        return '{"intent": "<script>alert(1)</script>"}'

    patch_chat_complete(_malicious_llm)
    g = build_nutritionist_graph()

    final = await g.ainvoke(_make_state("balabala"))

    # intent 字段必须是白名单中的值,不能是 LLM 原始输出
    assert final["intent"] in nodes.INTENT_TO_AGENT, (
        f"intent {final['intent']!r} 不在白名单 {set(nodes.INTENT_TO_AGENT.keys())} 内 —— "
        "Prometheus label cardinality 风险"
    )
    # 具体应该被收敛为 consult(默认意图)
    assert final["intent"] == "consult"
    assert final.get("selected_subagent") is None


@pytest.mark.asyncio
async def test_meal_plan_exception_details_do_not_leak_to_user(
    patch_chat_complete, patch_meal_plan
):
    """generate_meal_plan 抛错时,final_answer 必须是 generic 文案,不能含 exception 细节。

    防御:不要把 stacktrace / 数据库路径 / 内部组件名漏给用户。
    """

    async def _llm_stub(_prompt, **_):
        return '{"intent": "plan"}'

    secret_internal_detail = "milvus_host=10.0.1.42 collection=user_profile_v3 token=sk-abc123"

    async def _boom(*_, **__):
        raise RuntimeError(secret_internal_detail)

    patch_chat_complete(_llm_stub)
    patch_meal_plan(_boom)

    g = build_nutritionist_graph()
    final = await g.ainvoke(_make_state("生成方案"))

    # 链路必须完成(不能让 exception 冒到顶)
    assert "final_answer" in final
    # 关键:用户可见文案不能含任何 exception 细节
    assert secret_internal_detail not in final["final_answer"]
    assert "10.0.1.42" not in final["final_answer"]
    assert "milvus" not in final["final_answer"].lower()
    assert "token" not in final["final_answer"].lower()
    assert "RuntimeError" not in final["final_answer"]
    # 应该有用户友好的提示
    assert "稍后再试" in final["final_answer"] or "暂时不可用" in final["final_answer"]


@pytest.mark.asyncio
async def test_data_insight_exception_details_do_not_leak_to_user(
    patch_chat_complete, patch_dify_workflow
):
    """同上,data_insight 分支也必须做异常脱敏。"""

    async def _llm_stub(_prompt, **_):
        return '{"intent": "insight"}'

    secret = "dify_api_key=app-secret-xyz dsn=postgres://root:pwd@db:5432/health"

    async def _boom(*_, **__):
        raise ConnectionError(secret)

    patch_chat_complete(_llm_stub)
    patch_dify_workflow(_boom)

    g = build_nutritionist_graph()
    final = await g.ainvoke(_make_state("看一下我的趋势"))

    assert secret not in final["final_answer"]
    assert "dify_api_key" not in final["final_answer"]
    assert "postgres" not in final["final_answer"].lower()
    assert "ConnectionError" not in final["final_answer"]


# =========================================================================
# 规则分类层 — LLM 之前的关键词短路
# =========================================================================
@pytest.fixture
def llm_must_not_be_called(monkeypatch):
    """断言式 stub:任何 chat_complete 调用都立即让测试失败。

    专门用来证明 "规则层命中后真的没走 LLM",而不只是 "最终意图正确"。
    """
    async def _boom(_prompt, **_):
        raise AssertionError(
            "intent_router 在规则命中后不应再调用 chat_complete —— "
            "若触发此异常,说明规则层短路失败,LLM 兜底被白白触发了。"
        )

    monkeypatch.setattr(nodes, "chat_complete", _boom, raising=True)

    async def _empty(_prompt, **_):
        return "{}"

    # memory_node(extract_entities)与筛查 screen_step(槽位抽取)各自有 chat_complete;
    # 它们在「规则命中后的子 Agent」里被合法调用 —— 这里用 benign stub 让其离线、确定,
    # 同时 _boom 仍守住「intent_router 本身不得再调 LLM」这条核心断言。
    from app.agents.nutritionist import memory as memory_mod
    from app.agents.risk_screening import conversation as screening_conv

    monkeypatch.setattr(memory_mod, "chat_complete", _empty, raising=True)
    monkeypatch.setattr(screening_conv, "chat_complete", _empty, raising=True)


@pytest.mark.asyncio
async def test_rule_layer_screening_keyword_bypasses_llm(llm_must_not_be_called):
    """规则命中 "营养风险筛查" → 不调 LLM,直接路由到 risk_screening。"""
    g = build_nutritionist_graph()
    final = await g.ainvoke(_make_state("帮我做个营养风险筛查"))
    assert final["intent"] == "screening"
    assert final["selected_subagent"] == "risk_screening"


@pytest.mark.asyncio
async def test_rule_layer_plan_keyword_bypasses_llm(llm_must_not_be_called):
    """规则命中 "减脂方案" → 不调 LLM,直接路由到 meal_plan。"""
    # patch_meal_plan 不在这里 fixture,所以方案生成会进 exception 分支
    # 我们关心的是 intent 决策,exception 后的 final_answer 是 fallback 文案 —— 这正是设计
    g = build_nutritionist_graph()
    final = await g.ainvoke(_make_state("我想要一份减脂方案"))
    assert final["intent"] == "plan"
    assert final["selected_subagent"] == "meal_plan"


@pytest.mark.asyncio
async def test_rule_layer_insight_keyword_bypasses_llm(llm_must_not_be_called):
    """规则命中 "蛋白质达标" → 不调 LLM,直接路由到 data_insight。"""
    g = build_nutritionist_graph()
    final = await g.ainvoke(_make_state("我最近的蛋白质达标情况怎么样"))
    assert final["intent"] == "insight"
    assert final["selected_subagent"] == "data_insight"


@pytest.mark.asyncio
async def test_rule_layer_handles_full_width_digits(llm_must_not_be_called):
    """全角数字 "近３０天" 也应被 NFKC 归一化后命中 "近30天"。"""
    g = build_nutritionist_graph()
    final = await g.ainvoke(_make_state("看看我近３０天的睡眠情况"))
    assert final["intent"] == "insight"


@pytest.mark.asyncio
async def test_rule_layer_misses_falls_through_to_llm(patch_chat_complete):
    """非关键词命中的普通咨询应走到 LLM 兜底(LLM 是确实被调用的)。"""
    called = {"count": 0}

    async def _llm_stub(_prompt, **_):
        called["count"] += 1
        return '{"intent": "consult"}'

    patch_chat_complete(_llm_stub)
    g = build_nutritionist_graph()
    final = await g.ainvoke(_make_state("低 GI 主食一般有哪些好选择?"))
    assert final["intent"] == "consult"
    # 至少调用一次:intent_router LLM 兜底;memory_node 因消息长度 ok 也会调一次
    assert called["count"] >= 1


def test_intent_keywords_only_reference_whitelisted_intents():
    """规则表 INTENT_KEYWORDS 的所有 key 必须落在 INTENT_TO_AGENT 白名单内。

    防御:防止规则表配错让"unknown intent"绕过白名单泄到 state / metric。
    """
    bad = set(nodes.INTENT_KEYWORDS.keys()) - set(nodes.INTENT_TO_AGENT.keys())
    assert not bad, f"INTENT_KEYWORDS 含未授权意图: {bad}"


def test_classify_by_rules_returns_none_on_empty_or_no_match():
    """空消息 / 无关键词 → 返回 None,让上层走 LLM。"""
    assert nodes._classify_by_rules("") is None
    assert nodes._classify_by_rules("   ") is None
    assert nodes._classify_by_rules("今天天气真好") is None


# =========================================================================
# 契约层 — INTENT_TO_AGENT 必须覆盖 INTENT_PROMPT 声明的所有类别
# =========================================================================
def test_intent_to_agent_map_covers_all_documented_intents():
    """防止有人在 INTENT_PROMPT 加了新意图但忘记加 INTENT_TO_AGENT 映射。"""
    documented = {"screening", "plan", "insight", "consult"}
    mapped = set(nodes.INTENT_TO_AGENT.keys())
    assert documented == mapped, (
        f"INTENT_PROMPT 声明的意图 {documented} 与映射 {mapped} 不一致"
    )
