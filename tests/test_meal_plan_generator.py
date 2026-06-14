"""meal_plan generator 编排 + 引用接地 单测 —— monkeypatch 检索/LLM,无 Milvus/网络,进 CI。

generate_meal_plan = 检索取证 → 拼 prompt → LLM 出 JSON → validate_plan_strict。
本测试用确定性 stub 替掉「检索」与「LLM」,聚焦验证编排正确 + **「证据引用必带 KB 来源」**
这条核心契约:LLM 若引用了本次检索证据之外的来源(幻觉来源)/ 漏引用,必须被拒。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.agents.meal_plan import generator

_EVIDENCE = [
    {"doc_id": "dietary_guide_2022_excerpt", "chunk_id": "0", "text": "少盐少油,控糖限酒。"},
    {"doc_id": "food_composition_excerpt", "chunk_id": "3", "text": "燕麦 GI 55。"},
]
_GOOD_REF = "dietary_guide_2022_excerpt:0"


def _seven_day_plan(citation: str) -> dict:
    item = {"name": "燕麦", "portion_g": 60, "kcal": 220, "citations": [citation]}
    day = {"breakfast": [item], "lunch": [item], "dinner": [item], "snack": [],
           "total_kcal": 1800, "macros": {"carb": 0.55, "protein": 0.18, "fat": 0.27}}
    return {"user_id": "u", "target_kcal": 1800,
            "days": [{**day, "day": i + 1} for i in range(7)]}


def _patch(monkeypatch, *, plan: dict, evidence=_EVIDENCE):
    async def _fake_retrieve(*a, **k):
        return list(evidence)

    async def _fake_llm(*a, **k):
        return json.dumps(plan, ensure_ascii=False)

    monkeypatch.setattr(generator, "retrieve_plan_evidence", _fake_retrieve)
    monkeypatch.setattr(generator, "chat_complete", _fake_llm)


def _run(profile=None):
    return asyncio.run(generator.generate_meal_plan(profile or {"user_id": "u"}))


def test_happy_path_returns_validated_grounded_plan(monkeypatch):
    _patch(monkeypatch, plan=_seven_day_plan(_GOOD_REF))
    plan = _run()
    assert len(plan["days"]) == 7
    # 每条食材引用都落在本次检索证据里
    refs = {f"{e['doc_id']}:{e['chunk_id']}" for e in _EVIDENCE}
    for day in plan["days"]:
        for slot in ("breakfast", "lunch", "dinner", "snack"):
            for item in day.get(slot) or []:
                assert item["citations"]
                assert all(c in refs for c in item["citations"])


def test_hallucinated_citation_is_rejected(monkeypatch):
    """LLM 引用了检索证据之外的来源(幻觉)→ validate_plan_strict 必须拒(抛错)。"""
    _patch(monkeypatch, plan=_seven_day_plan("ghost_doc:9"))
    with pytest.raises(ValueError, match="不存在"):
        _run()


def test_missing_citation_is_rejected(monkeypatch):
    """食材漏引用 → Pydantic min_length=1 拒。"""
    bad = _seven_day_plan(_GOOD_REF)
    bad["days"][0]["breakfast"][0]["citations"] = []
    _patch(monkeypatch, plan=bad)
    with pytest.raises(Exception):
        _run()


def test_short_plan_is_rejected(monkeypatch):
    """不足 7 天 → schema/Pydantic 拒。"""
    bad = _seven_day_plan(_GOOD_REF)
    bad["days"] = bad["days"][:6]
    _patch(monkeypatch, plan=bad)
    with pytest.raises(Exception):
        _run()


def test_defaults_filled_when_llm_omits(monkeypatch):
    """LLM 漏 user_id/plan_id/target_kcal 时由 generator 兜底补齐。"""
    plan = _seven_day_plan(_GOOD_REF)
    del plan["user_id"]
    del plan["target_kcal"]
    _patch(monkeypatch, plan=plan)
    out = _run({"user_id": "demo-7"})
    assert out["user_id"] == "demo-7"
    assert out["target_kcal"] > 0
