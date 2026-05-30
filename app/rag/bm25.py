"""轻量内存 BM25 索引。

适合知识库规模 <= 100w chunk 的场景；更大规模建议换 Elasticsearch / OpenSearch。
索引从 ingestion 生成的 jsonl 加载，进程级缓存。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.config import get_settings

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[一-龥]")


def tokenize(text: str) -> list[str]:
    """中文按字、英文按词的简单分词，配合 BM25 已经足够实用。"""
    return _TOKEN_RE.findall(text.lower())


@lru_cache(maxsize=8)
def _index(collection: str) -> tuple[BM25Okapi, list[dict]]:
    s = get_settings()
    path = Path(s.model_cache_dir).parent / "bm25" / f"{collection}.jsonl"
    if not path.exists():
        return BM25Okapi([["__empty__"]]), []
    docs: list[dict] = []
    tokens: list[list[str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            docs.append(d)
            tokens.append(tokenize(d["text"]))
    return BM25Okapi(tokens), docs


def bm25_search(collection: str, query: str, top_k: int = 50) -> list[dict]:
    bm25, docs = _index(collection)
    if not docs:
        return []
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(
        ((s, d) for s, d in zip(scores, docs, strict=True) if s > 0),
        key=lambda x: x[0],
        reverse=True,
    )[:top_k]
    return [
        {
            "doc_id": d["doc_id"],
            "chunk_id": d["chunk_id"],
            "text": d["text"],
            "metadata": d.get("metadata", {}),
            "bm25_score": float(s),
        }
        for s, d in ranked
    ]


def reload_indices() -> None:
    """重建知识库后调用，清空 BM25 缓存。"""
    _index.cache_clear()
