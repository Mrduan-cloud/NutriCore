"""Prometheus 指标 — 暴露在 /metrics。

业务指标：
- nutricore_llm_requests_total{model,status}
- nutricore_llm_latency_seconds{model}
- nutricore_rag_retrieval_seconds{collection}
- nutricore_agent_invocations_total{agent}
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

llm_requests = Counter(
    "nutricore_llm_requests_total",
    "LLM 请求次数",
    ["model", "status"],
)
llm_latency = Histogram(
    "nutricore_llm_latency_seconds",
    "LLM 单次请求耗时",
    ["model"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)
rag_latency = Histogram(
    "nutricore_rag_retrieval_seconds",
    "RAG 混合检索耗时",
    ["collection"],
    buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 5),
)
agent_invocations = Counter(
    "nutricore_agent_invocations_total",
    "Agent 调用次数",
    ["agent", "outcome"],
)


async def metrics_endpoint(request: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
