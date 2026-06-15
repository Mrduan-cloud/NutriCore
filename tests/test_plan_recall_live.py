"""meal_plan RAG 真实召回评测(集成测试,需 Milvus + KB + BGE/重排权重)。

把 `app.evaluation.plan_eval.recall_at_k`(此前只用 stub retriever 验证算法)接到
**真实** `retrieve_plan_evidence` 管线(BM25 + BGE 向量 + RRF + Cross-Encoder),
对一组 gold(查询 → 应命中的 KB 文档)固化 recall@5 ≥ 0.8。

- **不在 CI allowlist**:依赖 Milvus / sentence-transformers / FlagReranker 重栈;
  本文件靠 `pytestmark` 在 Milvus 不可用 / 库未灌时自动 skip,不会误红。
- 种子 KB 仅 2 文档,doc 级 recall@5 容易偏高,故**额外断言 top-1 文档准确率**
  作为真正能抓排序退化的判别指标(reranker / embedding 坏掉会让 top-1 跑偏)。
- 跑法:栈起好 + 灌过 KB 后 `pytest tests/test_plan_recall_live.py -v`(容器内或本机)。
"""
from __future__ import annotations

import asyncio

import pytest

from app.evaluation.plan_eval import LIVE_RECALL_GOLD, recall_at_k

# gold（查询 → 应命中文档）与看板 live 路径共用，定义在 plan_eval.LIVE_RECALL_GOLD。
GOLD = LIVE_RECALL_GOLD


def _guide_ready() -> bool:
    """Milvus 可用且 guide 库已灌(>=6 实体)才跑,否则 skip。"""
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


pytestmark = pytest.mark.skipif(
    not _guide_ready(), reason="需要在线 Milvus + 已灌 dietary_guide_kb"
)


def _ranked_doc_ids(query: str) -> list[str]:
    """真实管线检索 → 按相关性排序的 doc_id 列表(每个命中 chunk 一项)。"""
    from app.agents.meal_plan.retriever import retrieve_plan_evidence

    ev = asyncio.run(retrieve_plan_evidence(query, top_k=20, rerank_top=8))
    return [e["doc_id"] for e in ev]


def test_recall_at_5_meets_bar():
    """headline 指标:真实管线 recall@5 ≥ 0.8。"""
    recall = recall_at_k(GOLD, _ranked_doc_ids, k=5)
    assert recall >= 0.8, f"recall@5={recall:.3f} < 0.8"


def test_top1_doc_accuracy_meets_bar():
    """判别指标:每条 query 的 top-1 chunk 应来自正确文档(抓排序退化)。"""
    correct = 0
    misses: list[str] = []
    for query, relevant in GOLD:
        ranked = _ranked_doc_ids(query)
        if ranked and ranked[0] in relevant:
            correct += 1
        else:
            misses.append(f"{query!r}->{ranked[:1]}")
    acc = correct / len(GOLD)
    assert acc >= 0.8, f"top1_doc_acc={acc:.3f} < 0.8; misses={misses}"
