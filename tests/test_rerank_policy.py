"""RAG 精排策略纯函数单测。

只测 ``_without_rerank`` / ``_merge_rerank_scores`` 两个纯函数 —— 不触发 Cross-Encoder
模型加载(那走 ``rerank()`` 的另一分支),所以 CI 轻量环境可跑。
"""

from app.core.embeddings import _merge_rerank_scores, _without_rerank


def _cands(n: int) -> list[dict]:
    return [
        {"doc_id": "d", "chunk_id": i, "text": f"t{i}", "rrf_score": (n - i) / 100}
        for i in range(n)
    ]


# ---------- _without_rerank(精排关闭:走召回顺序) ----------
def test_without_rerank_keeps_recall_order_and_truncates() -> None:
    out = _without_rerank(_cands(5), top_k=3)
    assert len(out) == 3
    assert [c["chunk_id"] for c in out] == [0, 1, 2]  # 召回顺序不变


def test_without_rerank_sets_score_from_rrf() -> None:
    out = _without_rerank([{"text": "x", "rrf_score": 0.03}], top_k=5)
    assert out[0]["rerank_score"] == 0.03


def test_without_rerank_missing_rrf_defaults_zero() -> None:
    out = _without_rerank([{"text": "x"}], top_k=5)
    assert out[0]["rerank_score"] == 0.0


def test_without_rerank_empty() -> None:
    assert _without_rerank([], 5) == []


# ---------- _merge_rerank_scores(精排开启时的纯计算部分) ----------
def test_merge_sorts_desc_and_truncates() -> None:
    cands = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    out = _merge_rerank_scores(cands, [0.1, 0.9, 0.5], top_k=2)
    assert [c["text"] for c in out] == ["b", "c"]
    assert out[0]["rerank_score"] == 0.9


def test_merge_handles_scalar_score() -> None:
    # FlagReranker 在单候选时返回 float 而非 list
    out = _merge_rerank_scores([{"text": "a"}], 0.7, top_k=5)
    assert out[0]["rerank_score"] == 0.7


def test_merge_preserves_candidate_fields() -> None:
    out = _merge_rerank_scores([{"text": "a", "doc_id": "d1", "chunk_id": 7}], [0.5], top_k=1)
    assert out[0]["doc_id"] == "d1"
    assert out[0]["chunk_id"] == 7
