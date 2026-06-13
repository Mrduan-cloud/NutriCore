"""RAG 子系统。

刻意**不**在包级 eager 导入子模块 —— ``hybrid_retrieval`` / ``ingestion`` /
``reranker`` 会拖入 pymilvus、sentence-transformers 等重型栈,放在 ``__init__``
里会让「导入任意 app.rag.* 子模块」(含纯逻辑的 ``bm25``)都被迫加载整条重依赖链,
在轻量环境(CI 纯逻辑测试)直接 ModuleNotFoundError。按需从子模块直接导入,例如::

    from app.rag.hybrid_retrieval import hybrid_search
    from app.rag.bm25 import bm25_search, reload_indices
"""
