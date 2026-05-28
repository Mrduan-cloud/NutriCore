"""主控状态机节点 — 真实意图识别 + 子 Agent 派发 + 引用核验 + 兜底。"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.agents.nutritionist.memory import extract_entities, merge_profile
from app.agents.nutritionist.prompts import CONSULT_SYSTEM, INTENT_PROMPT
from app.core.llm import chat_complete
from app.observability.metrics import agent_invocations


# 急重症 / 孕产期 —— 紧急,导向"尽快就医"
ACUTE_RISK_KEYWORDS = (
    "急救", "胸痛", "昏迷", "孕妇", "怀孕", "孕期", "化疗", "透析",
    "晕厥", "脑梗", "心梗", "出血",
)

# 慢性病 / 临床 / 用药 —— 涉及诊疗范畴,营养建议不能替代医疗,
# 导向"请专科医生 / 临床营养师评估"。把这类问题挡在 LLM 生成临床建议之前:
#   1. 合规:互联网健康咨询不提供疾病特异性临床/用药方案
#   2. 产品:营养 Agent 守住"营养陪伴"边界,不越界做诊疗
CLINICAL_KEYWORDS = (
    "高血压", "糖尿病", "痛风", "冠心病", "高血脂", "高尿酸", "肾病", "肝病",
    "甲亢", "甲减", "癌", "肿瘤", "确诊", "病情", "吃药", "用药", "药物",
    "剂量", "处方", "治疗", "诊断", "复查指标",
)

# 合并:任一命中都走安全兜底(safety_fallback)
HIGH_RISK_KEYWORDS = ACUTE_RISK_KEYWORDS + CLINICAL_KEYWORDS

INTENT_TO_AGENT = {
    "screening": "risk_screening",
    "plan": "meal_plan",
    "insight": "data_insight",
    "consult": None,
}

# 规则关键词层 —— 在 LLM 之前做一次低成本短路:
#   - 命中任意意图的关键词 → 直接返回该意图,跳过 LLM 调用
#   - 全部 miss → 回退到 LLM 分类
#
# 设计取舍:
#   - 仅收录"高置信"短语(如"NRS2002""七天食谱"这种几乎不会指向其他意图的)
#   - 避免引入"减肥""体重"这种模棱两可的词(它们可能属于 plan / consult / insight 任一)
#   - 关键词是大小写不敏感 + 全角半角宽容(NFKC 归一化)
#   - 任何关键词都必须仍然落在 INTENT_TO_AGENT 白名单内 —— 防止规则配置错误偷偷写出 unknown intent
INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "screening": (
        "营养风险筛查", "营养筛查", "NRS2002", "NRS-2002",
        "营养风险评估", "营养评估问卷",
    ),
    "plan": (
        "膳食计划", "膳食方案", "7天食谱", "七天食谱", "一周食谱",
        "营养方案", "减脂方案", "增肌方案", "控糖方案",
    ),
    "insight": (
        "近30天", "近 30 天", "近三十天", "过去一个月", "过去三个月",
        "近一周趋势", "蛋白质达标", "体重趋势", "睡眠趋势", "数据洞察",
    ),
}

# 用户可见的兜底文案 —— 不要泄漏 stacktrace / 内部组件名
_SUBAGENT_FAILURE_MESSAGES = {
    "meal_plan": "营养方案暂时不可用,稍后再试。如反复出现请联系管理员。",
    "data_insight": "健康数据查询暂时不可用,稍后再试。如反复出现请联系管理员。",
}


def _is_high_risk(text: str) -> bool:
    return any(k in text for k in HIGH_RISK_KEYWORDS)


def _classify_by_rules(text: str) -> str | None:
    """规则关键词分类。返回命中的意图(必在 INTENT_TO_AGENT 内)或 None。

    匹配策略:
    - 全角/半角 + 大小写不敏感(NFKC 归一化 + lower)
    - 任意意图的任意关键词命中即返回该意图
    - 多意图同时命中时,按 INTENT_KEYWORDS 字典顺序优先(screening > plan > insight)
      理由:这三个意图都对应"操作型"业务,优先级反映"用户决心更强"的方向
    """
    import unicodedata

    normalized = unicodedata.normalize("NFKC", text or "").lower()
    if not normalized:
        return None
    for intent, keywords in INTENT_KEYWORDS.items():
        if intent not in INTENT_TO_AGENT:
            # 配置自检:规则表写错也不能让未知意图泄出
            continue
        for kw in keywords:
            if unicodedata.normalize("NFKC", kw).lower() in normalized:
                return intent
    return None


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def _last_user_text(state: dict[str, Any]) -> str:
    """从消息历史中拿出最后一条用户消息的纯文本。

    LangChain 0.3 起 ``HumanMessage.content`` 不再保证是 ``str``:
    多模态/工具调用形态下,content 可能是 ``list[dict]``,形如::

        [{"type": "text", "text": "..."}, {"type": "image_url", ...}]

    若直接把 list 透传给下游 ``_is_high_risk`` 的 ``"急救" in text`` 检查,
    会变成"急救"是否是 list 元素 → **永远 False**,导致高风险关键词
    gate 被静默绕过。所以本函数必须把 ``list[dict]`` 的所有 ``type=text``
    块抽出来拼成单个字符串。
    """
    for msg in reversed(state.get("messages", []) or []):
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")
        if not content:
            continue
        # 多模态形态: list[dict] | list[str]
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(part, str):
                    parts.append(part)
            content = " ".join(parts).strip()
        if isinstance(content, str) and content:
            return content
    return ""


async def intent_router(state: dict[str, Any]) -> dict[str, Any]:
    """三层意图分类:高风险 gate → 规则关键词 → LLM 兜底。

    优先级与短路:
    1. **高风险关键词** (急救/胸痛/孕产期 ...) → 立即返回 risk_alert,
       不调 LLM、不调子 Agent。这是安全 gate,必须最先判定。
    2. **规则关键词分类** (INTENT_KEYWORDS) → 命中即返回对应意图,
       绕过 LLM。节省一次 ~200ms / ~150 token 的 LLM 调用,
       对高频固定句式(e.g. "做个 NRS2002 筛查")延迟显著下降。
    3. **LLM 兜底分类** → 规则未命中时调用 chat_complete + 白名单收敛。

    Metric label outcome 一律落在 INTENT_TO_AGENT 白名单内,防 cardinality 爆炸。
    """
    last_msg = _last_user_text(state)

    # ---- 第 1 层:高风险 gate ----
    if _is_high_risk(last_msg):
        agent_invocations.labels(agent="intent_router", outcome="high_risk").inc()
        return {"intent": "risk_alert", "selected_subagent": None, "is_high_risk": True}

    # ---- 第 2 层:规则关键词分类 ----
    rule_intent = _classify_by_rules(last_msg)
    if rule_intent is not None:
        # 规则结果走和 LLM 一样的白名单收敛 + metric 路径
        intent = rule_intent if rule_intent in INTENT_TO_AGENT else "consult"
        sub = INTENT_TO_AGENT[intent]
        agent_invocations.labels(agent="intent_router", outcome=f"rule:{intent}").inc()
        logger.debug("intent_router rule-hit -> {}", intent)
        return {"intent": intent, "selected_subagent": sub, "is_high_risk": False}

    # ---- 第 3 层:LLM 兜底 ----
    try:
        raw = await chat_complete(
            INTENT_PROMPT.format(user_message=last_msg),
            response_format="json",
            temperature=0.0,
            max_tokens=200,
        )
        raw_intent = _extract_json(raw).get("intent", "consult")
    except Exception as e:  # noqa: BLE001
        logger.warning("intent classify failed, fallback to consult: {}", e)
        raw_intent = "consult"

    # 白名单收敛 —— 防止恶意/异常 LLM 输出污染:
    # 1. Prometheus label cardinality(防 series 爆炸 OOM)
    # 2. state["intent"] 后续可能在审计 / 前端显示场景被使用
    intent = raw_intent if raw_intent in INTENT_TO_AGENT else "consult"
    if intent != raw_intent:
        logger.warning("intent '{}' not in whitelist, coerced to consult", raw_intent)

    sub = INTENT_TO_AGENT[intent]
    agent_invocations.labels(agent="intent_router", outcome=f"llm:{intent}").inc()
    return {"intent": intent, "selected_subagent": sub, "is_high_risk": False}


async def subagent_dispatcher(state: dict[str, Any]) -> dict[str, Any]:
    sub = state.get("selected_subagent")
    user_id = state.get("user_id", "anonymous")
    profile = state.get("user_profile", {})
    last_msg = _last_user_text(state)

    if sub == "risk_screening":
        return {
            "final_answer": (
                "我可以帮你做 **NRS-2002 营养风险筛查**。它从「疾病严重程度 + 营养状态 + 年龄」"
                "三个维度评分,帮你判断是否存在营养风险。\n\n"
                "我们从几个问题开始:\n"
                "1. 你最近 3 个月体重有没有明显下降?大概多少 kg?\n"
                "2. 最近一周进食量比平时减少了吗?\n"
                "3. 目前有没有正在治疗的疾病?\n\n"
                "把这几项告诉我,我来给你算分并解读。"
            ),
            "tool_calls": [{"tool": "risk_screening_intro"}],
        }

    if sub == "meal_plan":
        from app.agents.meal_plan.generator import generate_meal_plan
        try:
            plan = await generate_meal_plan(profile, user_request=last_msg)
            return {
                "final_answer": _format_meal_plan_md(plan),
                "tool_calls": [{"tool": "meal_plan.generate"}],
                "citations": _collect_citations(plan),
            }
        except Exception:  # noqa: BLE001
            # log 完整 stacktrace + request_id 便于排障;不要泄漏给用户
            logger.bind(request_id=state.get("request_id", "-"), user_id=user_id).exception(
                "meal_plan generation failed"
            )
            agent_invocations.labels(agent="subagent_dispatcher", outcome="meal_plan_error").inc()
            return {"final_answer": _SUBAGENT_FAILURE_MESSAGES["meal_plan"]}

    if sub == "data_insight":
        from app.agents.data_insight.dify_client import run_workflow
        try:
            result = await run_workflow(last_msg, user_id)
            return {
                "final_answer": _format_insight_md(result),
                "tool_calls": [{"tool": "data_insight.query"}],
                "extra": {"insight": result},
            }
        except Exception:  # noqa: BLE001
            logger.bind(request_id=state.get("request_id", "-"), user_id=user_id).exception(
                "data_insight workflow failed"
            )
            agent_invocations.labels(agent="subagent_dispatcher", outcome="insight_error").inc()
            return {"final_answer": _SUBAGENT_FAILURE_MESSAGES["data_insight"]}

    # 未知子 Agent (理论上不可达 —— _route 已经在前面短路掉 sub=None)
    return {"final_answer": f"未配置的子 Agent: {sub!r}"}


async def tool_executor(state: dict[str, Any]) -> dict[str, Any]:
    """工具调用审计 — 把 dispatcher 写入的 tool_calls 落审计日志。

    本节点目前是 audit-only(真实工具执行已由 dispatcher 完成),
    但仍必须返回非空 patch,否则 LangGraph 会抛 InvalidUpdateError
    (要求节点至少写入一个 schema 字段)—— 这里回写 tool_calls 自身作为 noop。
    """
    user_id = state.get("user_id", "anonymous")
    rid = state.get("request_id", "-")
    tool_calls = state.get("tool_calls", []) or []
    for call in tool_calls:
        logger.bind(audit=True, request_id=rid, user_id=user_id).info(
            "tool_call name={}", call.get("tool")
        )
    return {"tool_calls": tool_calls}


async def citation_validator(state: dict[str, Any]) -> dict[str, Any]:
    citations = state.get("citations", []) or []
    valid = [c for c in citations if isinstance(c, str) and ":" in c]
    return {"citations": valid}


def _format_profile(profile: dict[str, Any]) -> str:
    """把用户画像压成一行中文上下文,喂给营养师做个性化。"""
    if not profile:
        return "(暂无用户画像)"
    parts: list[str] = []
    label = {
        "age": "年龄", "gender": "性别", "height_cm": "身高cm",
        "weight_kg": "体重kg", "bmi": "BMI", "chronic_diseases": "慢病史",
        "allergies": "过敏源", "diet_preferences": "饮食偏好",
        "budget_per_day": "每日预算元",
    }
    for k, name in label.items():
        v = profile.get(k)
        if v in (None, "", [], {}):
            continue
        if isinstance(v, list):
            v = "、".join(map(str, v))
        parts.append(f"{name}={v}")
    return " / ".join(parts) if parts else "(暂无用户画像)"


# Cross-Encoder 相关性阈值:低于此分视为"知识库无关",不作为证据/引用。
# BGE reranker 原始 logit:相关通常为正,不相关为负(如运动问题 vs 饮食知识库)。
_CONSULT_RERANK_MIN = 0.0


async def consult_rag_context(query: str, top_k: int = 3) -> tuple[str, list[str]]:
    """为 consult 检索知识库并按相关性过滤,返回 (证据文本块, 真实引用列表)。

    流程:hybrid 召回 → Cross-Encoder 精排 → **只保留分数 ≥ 阈值的相关片段**。
    若没有任何片段足够相关(例如问运动、而库里只有饮食知识),返回 ('', []),
    答复将基于通用营养学,且**不挂任何引用**(避免"答运动却引饮食指南"的错误溯源)。
    """
    try:
        from app.config import get_settings
        from app.rag.hybrid_retrieval import hybrid_search
        from app.rag.reranker import cross_encoder_rerank

        s = get_settings()
        recalled = await hybrid_search(
            collection=s.milvus_collection_guide, query=query, top_k=12
        )
        ranked = cross_encoder_rerank(query, recalled, top_k=top_k) if recalled else []
    except Exception as e:  # noqa: BLE001
        logger.warning("consult retrieval failed, answering without RAG: {}", e)
        return "", []

    relevant = [c for c in ranked if c.get("rerank_score", -99) >= _CONSULT_RERANK_MIN]
    if not relevant:
        logger.debug("consult: no relevant KB chunk (top score too low), no citations")
        return "", []
    evidence = "\n".join(
        f"[{c.get('doc_id')}:{c.get('chunk_id')}] {(c.get('text') or '')[:200]}"
        for c in relevant
    )
    citations = [f"{c.get('doc_id')}:{c.get('chunk_id')}" for c in relevant]
    return evidence, citations


async def build_consult_prompt(query: str, profile: dict[str, Any]) -> tuple[str, list[str]]:
    """构建 consult 的用户 prompt + 返回真实引用(供同步节点与流式端点共用)。"""
    evidence, citations = await consult_rag_context(query)
    profile_ctx = _format_profile(profile)
    ref = evidence or "(知识库无直接匹配,可基于通用营养学回答)"
    prompt = (
        f"用户画像:{profile_ctx}\n\n"
        f"知识库参考:\n{ref}\n\n"
        f"用户问题:{query}\n\n"
        "请基于知识库参考与画像精炼作答(250 字内,先结论再要点)。"
    )
    return prompt, citations


async def general_consult(state: dict[str, Any]) -> dict[str, Any]:
    """一般营养咨询 —— consult 意图的真实回答节点(RAG 接地)。

    检索知识库 → 把证据喂给 LLM → 返回真实引用。
    没有这个节点的话,consult 在 _route 里会直接到 END,导致"普通对话无回答"。
    """
    last_msg = _last_user_text(state)
    prompt, citations = await build_consult_prompt(last_msg, state.get("user_profile", {}))
    try:
        answer = await chat_complete(
            prompt,
            system=CONSULT_SYSTEM,
            temperature=0.3,
            max_tokens=600,
        )
    except Exception:  # noqa: BLE001
        logger.bind(
            request_id=state.get("request_id", "-"),
            user_id=state.get("user_id", "anonymous"),
        ).exception("general_consult LLM failed")
        agent_invocations.labels(agent="general_consult", outcome="error").inc()
        return {"final_answer": "营养咨询暂时不可用,稍后再试。"}

    # 兜底:剥离模型可能仍残留的 [source: ...] 标记
    cleaned = re.sub(r"\[source:[^\]]*\]", "", answer or "").strip()
    agent_invocations.labels(agent="general_consult", outcome="ok").inc()
    return {
        "final_answer": cleaned or "我在,请把你的营养问题说得具体一些。",
        "citations": citations,
    }


async def safety_fallback(state: dict[str, Any]) -> dict[str, Any]:
    fallback = (
        "你的问题涉及具体疾病、用药或临床医疗范畴。营养建议不能替代专业诊疗,"
        "为了你的安全,建议前往正规医院,由专科医生或临床营养师结合你的检查指标做评估。\n\n"
        "我可以帮你的是日常、非临床的营养话题,比如:\n"
        "· 减脂 / 增肌期的饮食结构怎么安排\n"
        "· 三餐怎么搭配更均衡、低 GI 主食有哪些\n"
        "· 某类食材的营养特点与替代方案\n\n"
        "换个这样的角度问我,我来帮你。"
    )
    agent_invocations.labels(agent="safety_fallback", outcome="triggered").inc()
    return {"final_answer": fallback, "is_high_risk": True}


async def memory_node(state: dict[str, Any]) -> dict[str, Any]:
    """从用户消息抽取画像字段并增量合入 user_profile。

    抽取失败 / 无新字段时,仍要返回带 user_profile 的 patch
    (LangGraph 节点不能返回空 dict —— 会抛 InvalidUpdateError)。
    """
    existing = state.get("user_profile", {})
    last_msg = _last_user_text(state)
    increment = await extract_entities(last_msg)
    if increment:
        merged = await merge_profile(
            existing, increment, user_id=state.get("user_id", "")
        )
        return {"user_profile": merged}
    # noop:回写既有 profile 满足 channel 写入要求
    return {"user_profile": existing}


def _collect_citations(plan: dict) -> list[str]:
    out: list[str] = []
    for day in plan.get("days", []) or []:
        for slot in ("breakfast", "lunch", "dinner", "snack"):
            for item in day.get(slot, []) or []:
                out.extend(item.get("citations", []))
    return list(dict.fromkeys(out))


_SLOT_NAME = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}


def _format_meal_plan_md(plan: dict) -> str:
    """把生成的 7 天方案 dict 渲染成紧凑的对话内 Markdown(直接展示,不跳页)。"""
    target = plan.get("target_kcal")
    head = "已根据你的画像生成 **7 天个性化营养方案**"
    if target:
        head += f"(目标热量约 **{round(target)} kcal/天**)"
    lines = [head + ":"]
    for day in (plan.get("days") or [])[:7]:
        d = day.get("day", "?")
        tk = day.get("total_kcal")
        day_head = f"**第 {d} 天**" + (f" · 约 {round(tk)} kcal" if tk else "")
        lines.append("\n" + day_head)
        for slot, name in _SLOT_NAME.items():
            items = day.get(slot) or []
            if not items:
                continue
            foods = "、".join(
                f"{it.get('name', '')}"
                + (f"({round(it.get('portion_g'))}g)" if it.get("portion_g") else "")
                for it in items
            )
            lines.append(f"- {name}:{foods}")
    return "\n".join(lines)


def _format_insight_md(result: dict) -> str:
    """把数据洞察结果渲染成对话内 Markdown 摘要。"""
    if not result:
        return "暂时没有查询到你的健康数据。"
    summary = result.get("summary") or result.get("insight") or ""
    lines = ["已基于你的健康数据生成洞察:\n"]
    if summary:
        lines.append(str(summary))
    chart = result.get("chart")
    if chart:
        ctype = chart.get("type") if isinstance(chart, dict) else None
        lines.append(f"\n_(已生成{('「' + str(ctype) + '」' ) if ctype else ''}可视化图表数据)_")
    return "\n".join(lines)
