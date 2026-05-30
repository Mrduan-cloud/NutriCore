"""方案生成专用检索：BM25 + BGE 向量 多路召回 → RRF 融合 → Cross-Encoder 精排。"""
from __future__ import annotations

from collections.abc import Iterable

from app.config import get_settings
from app.rag.hybrid_retrieval import hybrid_search
from app.rag.reranker import cross_encoder_rerank


async def retrieve_plan_evidence(
    query: str,
    chronic_diseases: Iterable[str] = (),
    allergies: Iterable[str] = (),
    top_k: int = 20,
    rerank_top: int = 8,
) -> list[dict]:
    s = get_settings()
    cd = list(chronic_diseases)
    al = list(allergies)
    expanded_query = " ".join([query, *cd, *al]) if (cd or al) else query

    chunks = await hybrid_search(
        collection=s.milvus_collection_guide,
        query=expanded_query,
        top_k=top_k,
        filters={},  # 当前 metadata 未严格按疾病分桶；命中由 expanded_query 主导
    )
    return cross_encoder_rerank(query, chunks, top_k=rerank_top)
