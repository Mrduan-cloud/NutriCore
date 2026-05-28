"""vLLM (OpenAI 兼容) 客户端 — 带重试、Prometheus 埋点。"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from functools import lru_cache

from loguru import logger
from openai import AsyncOpenAI, APIError, APIConnectionError, APITimeoutError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.observability.metrics import llm_latency, llm_requests


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(
        base_url=s.llm_base_url,
        api_key=s.llm_api_key,
        timeout=s.llm_timeout,
        max_retries=0,  # 我们用 tenacity 自己管重试
    )


async def chat_complete(
    prompt: str | list[dict],
    *,
    response_format: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    system: str | None = None,
) -> str:
    s = get_settings()
    if isinstance(prompt, str):
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
    else:
        msgs = prompt

    kwargs: dict = {
        "model": s.llm_model,
        "messages": msgs,
        "temperature": s.llm_temperature if temperature is None else temperature,
    }
    if response_format == "json":
        kwargs["response_format"] = {"type": "json_object"}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type((APIError, APIConnectionError, APITimeoutError)),
        stop=stop_after_attempt(s.llm_max_retries),
        wait=wait_exponential(min=1, max=8),
        reraise=True,
    ):
        with attempt:
            t0 = time.perf_counter()
            try:
                resp = await _client().chat.completions.create(**kwargs)
            except Exception:
                llm_requests.labels(model=s.llm_model, status="error").inc()
                raise
            cost = time.perf_counter() - t0
            llm_latency.labels(model=s.llm_model).observe(cost)
            llm_requests.labels(model=s.llm_model, status="ok").inc()
            content = resp.choices[0].message.content or ""
            logger.debug("LLM ok in {:.2f}s, {} chars", cost, len(content))
            return content
    return ""  # unreachable


async def chat_complete_stream(
    prompt: str | list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    system: str | None = None,
) -> AsyncIterator[str]:
    """流式版 chat_complete —— 逐 token yield content delta。

    用于 SSE 端点做打字机效果。不走 tenacity 重试(流式重试语义复杂),
    出错直接抛给调用方处理。
    """
    s = get_settings()
    if isinstance(prompt, str):
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
    else:
        msgs = prompt

    kwargs: dict = {
        "model": s.llm_model,
        "messages": msgs,
        "temperature": s.llm_temperature if temperature is None else temperature,
        "stream": True,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    t0 = time.perf_counter()
    try:
        stream = await _client().chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception:
        llm_requests.labels(model=s.llm_model, status="error").inc()
        raise
    cost = time.perf_counter() - t0
    llm_latency.labels(model=s.llm_model).observe(cost)
    llm_requests.labels(model=s.llm_model, status="ok").inc()
    logger.debug("LLM stream done in {:.2f}s", cost)
