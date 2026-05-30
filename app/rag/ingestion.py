"""知识库构建：解析切分 + 元数据增强 + 向量化入库 + BM25 倒排索引。

切分策略：
- 优先按 Markdown 标题分段
- 再按字符数 + 重叠滑窗细切，避免跨段语义割裂
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from loguru import logger

from app.clients.milvus import upsert_chunks
from app.config import get_settings
from app.core.embeddings import embed_texts


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def split_document(
    doc_id: str,
    content: str,
    chunk_size: int = 500,
    overlap: int = 80,
    base_metadata: dict | None = None,
) -> list[Chunk]:
    base_metadata = base_metadata or {}
    chunks: list[Chunk] = []
    # 先按标题切大段
    sections: list[tuple[str, str]] = []
    cursor = 0
    cur_heading = ""
    for m in _HEADING_RE.finditer(content):
        if cursor < m.start():
            sections.append((cur_heading, content[cursor:m.start()].strip()))
        cur_heading = m.group(2).strip()
        cursor = m.end()
    if cursor < len(content):
        sections.append((cur_heading, content[cursor:].strip()))
    if not sections:
        sections = [("", content)]

    idx = 0
    step = max(1, chunk_size - overlap)
    for heading, text in sections:
        if not text:
            continue
        i = 0
        while i < len(text):
            piece = text[i : i + chunk_size]
            md = {**base_metadata, "heading": heading}
            chunks.append(Chunk(doc_id=doc_id, chunk_id=f"{doc_id}#{idx}", text=piece, metadata=md))
            i += step
            idx += 1
    return chunks


async def embed_and_upsert(chunks: Iterable[Chunk], collection: str) -> int:
    chunk_list = list(chunks)
    if not chunk_list:
        return 0
    vecs = embed_texts([c.text for c in chunk_list])
    payload = [
        {
            "doc_id": c.doc_id,
            "chunk_id": c.chunk_id,
            "text": c.text,
            "metadata": c.metadata,
            "embedding": v,
        }
        for c, v in zip(chunk_list, vecs, strict=True)
    ]
    n = upsert_chunks(collection, payload)
    logger.info("upserted {} chunks into {}", n, collection)
    return n


async def ingest_markdown_dir(source_dir: str | Path, collection: str, base_metadata: dict | None = None) -> int:
    """把目录里所有 .md 文件解析切分 + 向量化入库，并同时写一份 jsonl 给 BM25 用。"""
    source = Path(source_dir)
    if not source.exists():
        raise FileNotFoundError(source)

    all_chunks: list[Chunk] = []
    for p in source.rglob("*.md"):
        rel = p.relative_to(source).as_posix()
        md = {"path": rel, **(base_metadata or {})}
        all_chunks.extend(split_document(doc_id=p.stem, content=p.read_text(encoding="utf-8"), base_metadata=md))

    n = await embed_and_upsert(all_chunks, collection)

    # 同步写一份 BM25 倒排索引源数据
    s = get_settings()
    cache_dir = Path(s.model_cache_dir).parent / "bm25"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with (cache_dir / f"{collection}.jsonl").open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    logger.info("wrote BM25 source jsonl for {}", collection)
    return n
