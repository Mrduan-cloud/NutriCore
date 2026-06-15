"""方案 Agent 评测器 —— Plan 维度跑分（compliance / citation_hit / recall@k）。

可离线（CI pure-logic）评测的是两项确定性指标：
- **compliance_rate**：方案通过双层校验（jsonschema + Pydantic + 引用核验）的比例。
- **citation_hit_rate**：方案内引用能映射到检索证据的比例（比 compliance 更细——
  二元校验里只要一条引用越界整份方案就 fail，本指标按**引用条数**给部分 credit）。

**recall_at_k** 需真实检索（BM25 + BGE + RRF + Cross-Encoder，依赖 Milvus / 重型权重），
故实现为**注入式纯函数**：传入 `retriever(query) -> ranked doc_ids` 回调即可——
CI 用确定性 stub 验证召回计算正确性，W09 再接真实 `retrieve_plan_evidence` 跑真召回。

本模块只 import validator（jsonschema + Pydantic，已在 CI）+ metrics（dataclass），
**不 import** retriever.py（那会拉 rag → reranker 重栈），保持 CI-light。
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.agents.meal_plan.validator import validate_plan_strict
from app.evaluation.metrics import PlanMetric

_SLOTS = ("breakfast", "lunch", "dinner", "snack")


@dataclass(frozen=True)
class PlanCase:
    """一条方案评测用例：方案 dict + 本次检索证据。"""

    plan: dict
    evidence: list[dict]


def _iter_citations(plan: dict) -> Iterable[str]:
    for day in plan.get("days", []):
        for slot in _SLOTS:
            for item in day.get(slot) or []:
                yield from item.get("citations", [])


def _valid_refs(evidence: list[dict]) -> set[str]:
    return {f"{e['doc_id']}:{e['chunk_id']}" for e in evidence}


def compliance_rate(cases: list[PlanCase]) -> float:
    """通过双层校验（不抛异常）的方案占比。"""
    if not cases:
        return 0.0
    ok = 0
    for c in cases:
        # 校验失败的任何异常（jsonschema / Pydantic / 引用越界）都算「不合规」
        try:
            validate_plan_strict(c.plan, evidence=c.evidence)
        except Exception:
            continue
        ok += 1
    return ok / len(cases)


def citation_hit_rate(cases: list[PlanCase]) -> float:
    """所有方案的引用里，能映射到检索证据的比例（按引用条数加权）。"""
    total = hit = 0
    for c in cases:
        refs = _valid_refs(c.evidence)
        for cite in _iter_citations(c.plan):
            total += 1
            hit += cite in refs
    return hit / total if total else 0.0


def recall_at_k(
    gold: list[tuple[str, set[str]]],
    retriever: Callable[[str], list[str]],
    k: int = 5,
) -> float:
    """召回率@k —— 注入式。

    - `gold`：`[(query, 相关 doc_id 集合)]`
    - `retriever(query)`：返回**排序后的** doc_id 列表
    - recall@k = 各 query 的 |top-k ∩ 相关| / |相关| 的均值
    """
    scores = []
    for query, relevant in gold:
        if not relevant:
            continue
        topk = set(retriever(query)[:k])
        scores.append(len(topk & relevant) / len(relevant))
    return sum(scores) / len(scores) if scores else 0.0


def evaluate_plan(
    cases: list[PlanCase] | None = None,
    recall_gold: list[tuple[str, set[str]]] | None = None,
    retriever: Callable[[str], list[str]] | None = None,
    k: int = 5,
) -> PlanMetric:
    """组装 PlanMetric。

    compliance / citation 永远离线计算；recall **仅在同时提供 gold + retriever 时**
    计算（需真实检索），否则记 0.0（离线 CI 路径不评 recall，留 W09 接真实检索）。
    """
    cases = cases if cases is not None else GOLD_PLAN_CASES
    recall = (
        recall_at_k(recall_gold, retriever, k)
        if recall_gold is not None and retriever is not None
        else 0.0
    )
    return PlanMetric(
        recall_at_k=recall,
        citation_hit_rate=citation_hit_rate(cases),
        compliance_rate=compliance_rate(cases),
    )


# —— 内置样例方案集（合规、引用齐全），供离线跑分 / 看板演示 ——
# doc_id 取自真实 KB：app/data/kb/{dietary_guide_2022_excerpt,food_composition_excerpt}.md
_EVIDENCE = [
    {"doc_id": "dietary_guide_2022_excerpt", "chunk_id": "0", "text": "..."},
    {"doc_id": "food_composition_excerpt", "chunk_id": "3", "text": "..."},
]


def _seven_day_plan(user_id: str, target_kcal: float, citation: str) -> dict:
    item = {"name": "燕麦", "portion_g": 60, "kcal": 220, "citations": [citation]}
    base = {
        "breakfast": [item], "lunch": [item], "dinner": [item], "snack": [],
        "total_kcal": target_kcal, "macros": {"carb": 0.55, "protein": 0.18, "fat": 0.27},
    }
    days = [{**base, "day": i + 1} for i in range(7)]
    return {"user_id": user_id, "target_kcal": target_kcal, "days": days}


GOLD_PLAN_CASES: list[PlanCase] = [
    PlanCase(_seven_day_plan("demo-001", 1800, "dietary_guide_2022_excerpt:0"), _EVIDENCE),
    PlanCase(_seven_day_plan("demo-002", 2200, "food_composition_excerpt:3"), _EVIDENCE),
]

# —— recall@k 真实召回 gold（查询 → 应命中文档）——
# 接真实 `retrieve_plan_evidence` 时用（看板 live 路径 + tests/test_plan_recall_live.py 共用，DRY）。
# doc_id 取自种子 KB：app/data/kb/{food_composition_excerpt,dietary_guide_2022_excerpt}.md
_FOOD = "food_composition_excerpt"     # 具体食材成分数值
_GUIDE = "dietary_guide_2022_excerpt"  # 膳食准则 / 推荐量 / 慢病关注
LIVE_RECALL_GOLD: list[tuple[str, set[str]]] = [
    ("燕麦的能量和升糖指数是多少", {_FOOD}),
    ("鸡胸肉的蛋白质含量", {_FOOD}),
    ("西兰花含多少维生素C", {_FOOD}),
    ("北豆腐的钙含量高吗", {_FOOD}),
    ("高血压患者每天盐摄入上限是多少", {_GUIDE}),
    ("成人每日蔬菜推荐摄入量", {_GUIDE}),
    ("孕妇能量需求要增加多少", {_GUIDE}),
    ("高血脂应控制饱和脂肪占总能量的比例", {_GUIDE}),
]


def main() -> None:
    import json

    from app.evaluation.metrics import aggregate_dashboard

    # 离线路径不评 recall（需真实检索栈），看板里显示 0.0。
    print(json.dumps(aggregate_dashboard(evaluate_plan(GOLD_PLAN_CASES)),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
