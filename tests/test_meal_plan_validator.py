"""方案双层校验单测。"""
import pytest

from app.agents.meal_plan.validator import validate_plan_strict


def _make_plan(extra_day: dict | None = None) -> dict:
    item = {
        "name": "燕麦",
        "portion_g": 60,
        "kcal": 220,
        "citations": ["dietary_guide_2022_excerpt#0"],
    }
    day = {
        "day": 1,
        "breakfast": [item],
        "lunch": [item],
        "dinner": [item],
        "snack": [],
        "total_kcal": 1800,
        "macros": {"carb": 0.55, "protein": 0.18, "fat": 0.27},
    }
    days = []
    for i in range(7):
        d = dict(day)
        d["day"] = i + 1
        days.append(d)
    if extra_day:
        days[-1] = extra_day
    return {"user_id": "demo-001", "target_kcal": 1800, "days": days}


def test_valid_plan_passes():
    plan = _make_plan()
    evidence = [{"doc_id": "dietary_guide_2022_excerpt", "chunk_id": "0", "text": "..."}]
    out = validate_plan_strict(plan, evidence=evidence)
    assert len(out["days"]) == 7


def test_missing_citation_fails():
    plan = _make_plan()
    plan["days"][0]["breakfast"][0]["citations"] = []
    evidence = [{"doc_id": "dietary_guide_2022_excerpt", "chunk_id": "0", "text": "..."}]
    with pytest.raises(Exception):
        validate_plan_strict(plan, evidence=evidence)


def test_invalid_citation_fails():
    plan = _make_plan()
    plan["days"][0]["breakfast"][0]["citations"] = ["nonexistent:1"]
    evidence = [{"doc_id": "dietary_guide_2022_excerpt", "chunk_id": "0", "text": "..."}]
    with pytest.raises(ValueError):
        validate_plan_strict(plan, evidence=evidence)
