"""BGE Embedding + Cross-Encoder Reranker — 懒加载，本地缓存。"""
from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from loguru import logger

from app.config import get_settings


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer

    s = get_settings()
    logger.info("loading embedding model {} ...", s.embedding_model)
    return SentenceTransformer(
        s.embedding_model,
        cache_folder=s.model_cache_dir,
        device="cpu",
    )


@lru_cache(maxsize=1)
def _reranker():
    from FlagEmbedding import FlagReranker

    s = get_settings()
    logger.info("loading reranker {} ...", s.reranker_model)
    return FlagReranker(s.reranker_model, use_fp16=False)


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """批量 embed — 归一化后输出，配合 IP 距离做近似余弦。"""
    if not texts:
        return []
    vecs = _embedder().encode(
        list(texts),
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vecs]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def rerank(query: str, candidates: list[dict], top_k: int = 8) -> list[dict]:
    """对 candidates 用 Cross-Encoder 精排，写入 rerank_score 并按其降序。

    提速旋钮(见 ``config.rag_rerank_*``,Cross-Encoder 在 CPU 上是首 token 前的主要阻塞):
    - ``rag_rerank_enabled=False`` → 跳过 Cross-Encoder,直接走 RRF 召回顺序;
    - 仅对前 ``rag_rerank_max_candidates`` 个候选打分(CPU 耗时≈线性于候选数)。
    """
    if not candidates:
        return []
    s = get_settings()
    if not s.rag_rerank_enabled:
        return _without_rerank(candidates, top_k)
    cands = candidates[: max(1, s.rag_rerank_max_candidates)]
    pairs = [(query, c["text"]) for c in cands]
    scores = _reranker().compute_score(pairs)
    return _merge_rerank_scores(cands, scores, top_k)


def _without_rerank(candidates: list[dict], top_k: int) -> list[dict]:
    """精排关闭:用召回(RRF)顺序,补 rerank_score=rrf_score 以兼容下游阈值过滤。纯函数。"""
    return [{**c, "rerank_score": float(c.get("rrf_score", 0.0))} for c in candidates[:top_k]]


def _merge_rerank_scores(candidates: list[dict], scores, top_k: int) -> list[dict]:
    """把 Cross-Encoder 分写回候选并按分降序截断 top_k。纯函数(给定 scores)。"""
    if isinstance(scores, float):
        scores = [scores]
    out = [{**c, "rerank_score": float(sc)} for c, sc in zip(candidates, scores, strict=True)]
    out.sort(key=lambda x: x["rerank_score"], reverse=True)
    return out[:top_k]
