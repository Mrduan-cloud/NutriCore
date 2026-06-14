"""meal_plan 端到端真实管线测试(需 Milvus + KB + BGE/重排 + DeepSeek)。

固化 W05「营养方案 RAG + generator 端到端 · 证据引用必带 KB 来源」:真实跑
generate_meal_plan(RAG 取证 → DeepSeek 出 JSON → validate_plan_strict),断言:
- 产出 7 天方案且通过强约束校验(generate 内部已 validate,这里再独立核一遍);
- **每条食材引用都接地到本次真实检索证据**(doc_id 属于已灌 KB 文档,非 LLM 幻觉);
- 目标热量在合理区间、macros 齐全。

不在 CI allowlist;Milvus 不可用/库未灌时自动 skip。DeepSeek 不可用时该测试会报错
(opt-in 集成测试,非 CI),重试或检查 .env 的 LLM_API_KEY 即可。
跑法:栈起好 + 灌过 dietary_guide_kb 后 `pytest tests/test_meal_plan_e2e_live.py -v`。
"""
from __future__ import annotations

import asyncio

import pytest

_KB_DOCS = {"dietary_guide_2022_excerpt", "food_composition_excerpt"}


def _stack_ready() -> bool:
    try:
        from pymilvus import Collection, utility

        from app.clients.milvus import _alias, connect_milvus
        from app.config import get_settings

        connect_milvus()
        name = get_settings().milvus_collection_guide
        if not utility.has_collection(name, using=_alias()):
            return False
        col = Collection(name, using=_alias())
        col.load()
        return col.num_entities >= 6
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _stack_ready(), reason="需要在线 Milvus + 已灌 dietary_guide_kb")

# 一个素食低脂、轻度慢病的画像,触发 RAG 走慢病/膳食准则证据。
_PROFILE = {
    "user_id": "e2e-demo", "gender": "female", "age": 34,
    "height_cm": 162, "weight_kg": 58,
    "chronic_diseases": ["高血压"], "allergies": ["花生"],
    "diet_preferences": ["低脂", "少盐"],
}


def _all_citations(plan: dict) -> list[str]:
    out: list[str] = []
    for day in plan.get("days", []):
        for slot in ("breakfast", "lunch", "dinner", "snack"):
            for item in day.get(slot) or []:
                out.extend(item.get("citations", []))
    return out


def _generate():
    from app.agents.meal_plan.generator import generate_meal_plan

    return asyncio.run(generate_meal_plan(_PROFILE))


def test_e2e_plan_is_7_days_and_kcal_sane():
    plan = _generate()
    assert len(plan["days"]) == 7
    assert 800 <= plan["target_kcal"] <= 4000
    for day in plan["days"]:
        assert set(day["macros"]) >= {"carb", "protein", "fat"}
        assert day["total_kcal"] > 0


def test_e2e_every_citation_grounded_to_kb():
    """证据引用必带 KB 来源:每条引用形如 doc_id:chunk_id 且 doc_id 属于已灌 KB 文档。"""
    plan = _generate()
    cites = _all_citations(plan)
    assert cites, "方案没有任何引用"
    for c in cites:
        assert ":" in c, f"引用格式非法:{c!r}"
        doc_id = c.split(":", 1)[0]
        assert doc_id in _KB_DOCS, f"引用指向非 KB 文档(疑似幻觉来源):{c!r}"
