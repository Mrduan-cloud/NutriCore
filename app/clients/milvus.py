"""Milvus 客户端封装。

提供：
- ensure_collection: 幂等建集合 (schema + index)
- upsert / search / delete
- 健康检查
"""
from __future__ import annotations

from functools import lru_cache

from loguru import logger
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from app.config import get_settings


def _alias() -> str:
    return "default"


@lru_cache(maxsize=1)
def connect_milvus() -> bool:
    s = get_settings()
    connections.connect(
        alias=_alias(),
        host=s.milvus_host,
        port=str(s.milvus_port),
        user=s.milvus_user or None,
        password=s.milvus_password or None,
    )
    logger.info("connected to Milvus {}:{}", s.milvus_host, s.milvus_port)
    return True


def is_healthy() -> bool:
    try:
        connect_milvus()
        return utility.list_collections(using=_alias()) is not None
    except Exception as e:
        logger.warning("milvus health failed: {}", e)
        return False


def ensure_collection(name: str, dim: int, description: str = "") -> Collection:
    """幂等建集合：固定 schema [pk, doc_id, chunk_id, text, metadata, embedding]，HNSW 索引。"""
    connect_milvus()
    if utility.has_collection(name, using=_alias()):
        return Collection(name, using=_alias())

    fields = [
        FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=4096),
        FieldSchema(name="metadata", dtype=DataType.JSON),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(fields=fields, description=description or name)
    col = Collection(name=name, schema=schema, using=_alias())
    col.create_index(
        field_name="embedding",
        index_params={
            "metric_type": "IP",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 200},
        },
    )
    col.load()
    logger.info("created Milvus collection {} (dim={})", name, dim)
    return col


def upsert_chunks(collection: str, chunks: list[dict]) -> int:
    """批量写入。每条 chunk 形如 {doc_id, chunk_id, text, metadata, embedding}。"""
    if not chunks:
        return 0
    col = ensure_collection(collection, dim=len(chunks[0]["embedding"]))
    data = [
        [c["doc_id"] for c in chunks],
        [c["chunk_id"] for c in chunks],
        [c["text"][:4000] for c in chunks],
        [c.get("metadata", {}) for c in chunks],
        [c["embedding"] for c in chunks],
    ]
    col.insert(data)
    col.flush()
    return len(chunks)


def search_vectors(
    collection: str,
    query_vec: list[float],
    top_k: int = 20,
    expr: str | None = None,
) -> list[dict]:
    """向量召回 — 返回带 doc_id/chunk_id/text/score 的 dict 列表。"""
    connect_milvus()
    if not utility.has_collection(collection, using=_alias()):
        return []
    col = Collection(collection, using=_alias())
    col.load()
    results = col.search(
        data=[query_vec],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"ef": 64}},
        limit=top_k,
        expr=expr,
        output_fields=["doc_id", "chunk_id", "text", "metadata"],
    )
    out: list[dict] = []
    for hit in results[0]:
        out.append(
            {
                "doc_id": hit.entity.get("doc_id"),
                "chunk_id": hit.entity.get("chunk_id"),
                "text": hit.entity.get("text"),
                "metadata": hit.entity.get("metadata") or {},
                "score": float(hit.score),
            }
        )
    return out


def drop_collection(name: str) -> None:
    connect_milvus()
    if utility.has_collection(name, using=_alias()):
        utility.drop_collection(name, using=_alias())
        logger.warning("dropped collection {}", name)
