"""BM25 内存索引缓存失效契约 —— 纯逻辑(rank_bm25),CI 可跑。

回归 code-review 抓到的一致性缺口:``ingest_markdown_dir`` 重写 BM25 jsonl 后必须
失效 ``_index`` 的 ``@lru_cache``,否则同一长驻进程仍用旧索引(向量库却已更新)→ 混检。
本测试直接验证「不 reload → 陈旧;reload 后 → 新鲜」这条契约。

注:语料至少 2 篇 —— BM25 的 IDF=log((N-n+0.5)/(n+0.5)),若查询词出现在**全部**
文档(单文档语料)IDF 为负,会被 ``bm25_search`` 的 ``score>0`` 过滤掉。
"""
from __future__ import annotations

import json

from app.rag import bm25

# 1 篇相关(命中"燕麦")+ 2 篇噪声(不含)。需 ≥3 篇:BM25 IDF=log((N-n+0.5)/(n+0.5)),
# 词在 n=1 篇时要 N>2 才 IDF>0,否则会被 bm25_search 的 score>0 过滤掉。
_NOISE = [
    {"doc_id": "noise1", "chunk_id": "noise1#0", "text": "三文鱼 蛋白质 脂肪 深海鱼"},
    {"doc_id": "noise2", "chunk_id": "noise2#0", "text": "西兰花 维生素 钙 蔬菜"},
]


def _write_corpus(path, relevant_doc_id: str) -> None:
    rel = {"doc_id": relevant_doc_id, "chunk_id": f"{relevant_doc_id}#0",
           "text": "燕麦 升糖指数 营养 主食 全谷物"}
    lines = [json.dumps(d, ensure_ascii=False) for d in (rel, *_NOISE)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_bm25_cache_is_stale_until_reload(tmp_path, monkeypatch):
    class _S:
        model_cache_dir = str(tmp_path / "models")

    def _stub_settings():  # ruff PLW0108: 不用 lambda
        return _S()

    # _index 读 Path(model_cache_dir).parent / "bm25" / col.jsonl
    monkeypatch.setattr(bm25, "get_settings", _stub_settings)
    (tmp_path / "bm25").mkdir()
    jsonl = tmp_path / "bm25" / "col.jsonl"
    bm25.reload_indices()  # 清掉别的用例可能留下的缓存

    _write_corpus(jsonl, "A")
    hit = bm25.bm25_search("col", "燕麦", top_k=5)
    assert hit and hit[0]["doc_id"] == "A"

    # 改写 jsonl(相关篇换成 B)但**不** reload → 仍命中旧 A,证明缓存陈旧
    _write_corpus(jsonl, "B")
    assert bm25.bm25_search("col", "燕麦", top_k=5)[0]["doc_id"] == "A"

    # reload 后 → 命中新的 B
    bm25.reload_indices()
    assert bm25.bm25_search("col", "燕麦", top_k=5)[0]["doc_id"] == "B"


def test_bm25_missing_jsonl_returns_empty(tmp_path, monkeypatch):
    class _S:
        model_cache_dir = str(tmp_path / "models")

    def _stub_settings():
        return _S()

    monkeypatch.setattr(bm25, "get_settings", _stub_settings)
    bm25.reload_indices()
    assert bm25.bm25_search("nope", "查询", top_k=5) == []
