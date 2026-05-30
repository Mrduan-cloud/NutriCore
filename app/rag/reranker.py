"""Cross-Encoder 精排 — 包一层 metric 埋点。"""
from __future__ import annotations

from collections.abc import Sequence

from app.core.embeddings import rerank


def cross_encoder_rerank(query: str, candidates: Sequence[dict], top_k: int = 8) -> list[dict]:
    return rerank(query, list(candidates), top_k=top_k)
