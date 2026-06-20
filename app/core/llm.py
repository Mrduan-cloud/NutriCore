"""多 LLM 适配层 —— LLMClient 协议 + OpenAI 兼容 / 原生 Anthropic 双 provider。

历史:本模块原为单一 vLLM(OpenAI 兼容)客户端。v1.1.0 抽出 `LLMClient` 协议
+ provider 工厂,新增原生 **Anthropic(Messages API)** provider(backlog 五个
provider 里唯一非 OpenAI 兼容的一档,需独立适配)。

设计要点:
- 公共函数 `chat_complete` / `chat_complete_stream` 签名不变,6 个调用点零改动
  (它们委派给 `get_llm_client()` 选出的 provider 实现)。
- `OpenAICompatClient` 覆盖 vLLM / Ollama / DeepSeek / Qwen / OpenAI(切换只改
  base_url / model / key,同旧行为)。
- `AnthropicClient` 走原生 Messages API:`system` 是顶层参数、`max_tokens` 必填、
  无 `response_format`(json 模式靠 system 指令)、流式走 `messages.stream()`。
  注:现代 Claude 模型(Opus 4.8/4.7)拒绝 `temperature` → 本适配层不透传,
  靠 prompt 引导(官方推荐做法)。
- `anthropic` 是**可选 provider 依赖**,仅在选用该 provider 时惰性 import,使本
  模块在不装 anthropic 的轻量环境(CI / 纯逻辑测试)仍可导入。
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Protocol

from loguru import logger
from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.observability.metrics import llm_latency, llm_requests

# JSON 模式指令:Anthropic 无 OpenAI 的 response_format={"type":"json_object"},
# 用 system 指令兜(跨模型通用,比 output_config.json_schema 更轻——调用方只传
# response_format="json" 这个 flag、不给 schema)。
_JSON_INSTRUCTION = "只输出合法 JSON,不要任何解释文字,不要 Markdown 代码围栏。"


# ===================== 纯函数:请求/响应映射(SDK 无关,离线可单测) =====================


def _build_messages(prompt: str | list[dict], system: str | None) -> list[dict]:
    """str|list[dict] + system → OpenAI 风格 messages(system 作为首条消息)。

    与旧实现行为一致:list 形式的 prompt 视为已成型 messages,**忽略** system kwarg。
    """
    if not isinstance(prompt, str):
        return list(prompt)
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return msgs


def _split_system(
    prompt: str | list[dict], system: str | None
) -> tuple[str | None, list[dict]]:
    """Anthropic 专用:把 system 提到顶层参数,messages 仅保留 user/assistant。

    Anthropic Messages API 不接受 role=system 的消息条目,需抽到顶层 `system`。
    返回 (system_str|None, messages)。
    """
    sys_parts: list[str] = []
    if system:
        sys_parts.append(system)
    msgs: list[dict] = []
    if isinstance(prompt, str):
        msgs.append({"role": "user", "content": prompt})
    else:
        for m in prompt:
            if m.get("role") == "system":
                if m.get("content"):
                    sys_parts.append(m["content"])
            else:
                msgs.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    sys_str = "\n\n".join(p for p in sys_parts if p) or None
    if not msgs:
        # 退化输入(list prompt 仅含 system 条目):Anthropic 要求 messages 非空 →
        # 把 system 降级为一条 user 消息(内容不丢),避免不可读的 API 400。
        return None, [{"role": "user", "content": sys_str or "(empty)"}]
    return sys_str, msgs


def _to_anthropic_request(
    prompt: str | list[dict],
    *,
    system: str | None,
    response_format: str | None,
    max_tokens: int | None,
    model: str,
    default_max_tokens: int,
) -> dict:
    """构造 Anthropic messages.create 请求体(纯函数)。"""
    sys_str, msgs = _split_system(prompt, system)
    if response_format == "json":
        sys_str = f"{sys_str}\n\n{_JSON_INSTRUCTION}" if sys_str else _JSON_INSTRUCTION
    req: dict = {
        "model": model,
        "messages": msgs,
        "max_tokens": max_tokens or default_max_tokens,
    }
    if sys_str:
        req["system"] = sys_str
    return req


def _extract_text(content) -> str:
    """Anthropic 响应 content(text/其他 block 混排)→ 纯文本。

    block 兼容对象(.type/.text)与 dict({"type","text"}),只取 text 块。
    """
    parts: list[str] = []
    for b in content or []:
        btype = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
        if btype == "text":
            txt = b.get("text") if isinstance(b, dict) else getattr(b, "text", None)
            if txt:
                parts.append(txt)
    return "".join(parts)


def _strip_code_fences(text: str) -> str:
    """剥去 LLM 偶发的 Markdown 代码围栏(```json … ``` / ``` … ```)。

    Anthropic json 模式靠 system 指令(非强约束),模型可能仍裹围栏 → 防御性剥离,
    与 OpenAI 的 response_format=json_object(保证无围栏)口径对齐。同 MediRead/NutriCore
    既有 `_unwrap_sql` 剥围栏思路。无围栏则原样返回。
    """
    s = text.strip()
    if not s.startswith("```"):
        return text
    nl = s.find("\n")
    if nl == -1:  # 只有一行 ``` 之类,不动
        return text
    body = s[nl + 1 :]  # 去掉首行 ```lang
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()


# ===================== 协议 =====================


class LLMClient(Protocol):
    """provider 适配层统一接口。两个方法签名与历史公共函数保持一致。"""

    async def chat_complete(
        self,
        prompt: str | list[dict],
        *,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> str: ...

    def chat_complete_stream(
        self,
        prompt: str | list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]: ...


# ===================== OpenAI 兼容 provider(vLLM/Ollama/DeepSeek/Qwen/OpenAI) =====================


class OpenAICompatClient:
    """OpenAI 兼容协议客户端。`sdk_client` 可注入(测试用),否则惰性按 settings 构建。"""

    def __init__(self, sdk_client: AsyncOpenAI | None = None) -> None:
        self._sdk = sdk_client

    @property
    def _client(self) -> AsyncOpenAI:
        if self._sdk is None:
            s = get_settings()
            self._sdk = AsyncOpenAI(
                base_url=s.llm_base_url,
                api_key=s.llm_api_key,
                timeout=s.llm_timeout,
                max_retries=0,  # 我们用 tenacity 自己管重试
            )
        return self._sdk

    async def chat_complete(
        self,
        prompt: str | list[dict],
        *,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> str:
        s = get_settings()
        msgs = _build_messages(prompt, system)
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
                    resp = await self._client.chat.completions.create(**kwargs)
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
        self,
        prompt: str | list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """流式版 —— 逐 token yield content delta(不走 tenacity,出错直接抛)。"""
        s = get_settings()
        msgs = _build_messages(prompt, system)
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
            stream = await self._client.chat.completions.create(**kwargs)
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


# ===================== 原生 Anthropic provider(Messages API) =====================


class AnthropicClient:
    """原生 Anthropic Messages API 客户端。

    与 OpenAI 兼容档的差异:system 顶层参数、max_tokens 必填、json 靠 system 指令、
    流式走 messages.stream()、不透传 temperature(现代模型拒绝)。
    `anthropic` 惰性 import,使本模块在不装 anthropic 的环境仍可导入。
    """

    def __init__(self, sdk_client=None) -> None:
        self._sdk = sdk_client

    @property
    def _client(self):
        if self._sdk is None:
            from anthropic import AsyncAnthropic  # 惰性:可选 provider 依赖

            s = get_settings()
            self._sdk = AsyncAnthropic(
                api_key=s.anthropic_api_key,
                base_url=s.anthropic_base_url or None,
                timeout=s.llm_timeout,
                max_retries=0,  # tenacity 自己管
            )
        return self._sdk

    @staticmethod
    def _retry_exc() -> tuple:
        import anthropic  # 惰性:仅执行 SDK 路径时需要

        return (
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
        )

    async def chat_complete(
        self,
        prompt: str | list[dict],
        *,
        response_format: str | None = None,
        temperature: float | None = None,  # 现代 Claude 拒绝 temperature,刻意不透传
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> str:
        s = get_settings()
        req = _to_anthropic_request(
            prompt,
            system=system,
            response_format=response_format,
            max_tokens=max_tokens,
            model=s.anthropic_model,
            default_max_tokens=s.anthropic_max_tokens,
        )

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(self._retry_exc()),
            stop=stop_after_attempt(s.llm_max_retries),
            wait=wait_exponential(min=1, max=8),
            reraise=True,
        ):
            with attempt:
                t0 = time.perf_counter()
                try:
                    resp = await self._client.messages.create(**req)
                except Exception:
                    llm_requests.labels(model=s.anthropic_model, status="error").inc()
                    raise
                cost = time.perf_counter() - t0
                llm_latency.labels(model=s.anthropic_model).observe(cost)
                llm_requests.labels(model=s.anthropic_model, status="ok").inc()
                content = _extract_text(resp.content)
                if response_format == "json":
                    content = _strip_code_fences(content)
                logger.debug("Anthropic ok in {:.2f}s, {} chars", cost, len(content))
                return content
        return ""  # unreachable

    async def chat_complete_stream(
        self,
        prompt: str | list[dict],
        *,
        temperature: float | None = None,  # 同 chat_complete:不透传
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        s = get_settings()
        req = _to_anthropic_request(
            prompt,
            system=system,
            response_format=None,
            max_tokens=max_tokens,
            model=s.anthropic_model,
            default_max_tokens=s.anthropic_max_tokens,
        )

        t0 = time.perf_counter()
        try:
            async with self._client.messages.stream(**req) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield text
        except Exception:
            llm_requests.labels(model=s.anthropic_model, status="error").inc()
            raise
        cost = time.perf_counter() - t0
        llm_latency.labels(model=s.anthropic_model).observe(cost)
        llm_requests.labels(model=s.anthropic_model, status="ok").inc()
        logger.debug("Anthropic stream done in {:.2f}s", cost)


# ===================== 工厂 + 向后兼容公共 API =====================


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """按 settings.llm_provider 选 provider 实现(缓存单例)。"""
    provider = (get_settings().llm_provider or "openai").lower()
    if provider == "anthropic":
        return AnthropicClient()
    return OpenAICompatClient()


def reset_llm_client() -> None:
    """清工厂缓存——运行期切 provider / 测试用。"""
    get_llm_client.cache_clear()


async def chat_complete(
    prompt: str | list[dict],
    *,
    response_format: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    system: str | None = None,
) -> str:
    """向后兼容入口:委派给当前 provider。6 个调用点继续 import 本函数,零改动。"""
    return await get_llm_client().chat_complete(
        prompt,
        response_format=response_format,
        temperature=temperature,
        max_tokens=max_tokens,
        system=system,
    )


async def chat_complete_stream(
    prompt: str | list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    system: str | None = None,
) -> AsyncIterator[str]:
    """向后兼容流式入口:委派给当前 provider。"""
    async for delta in get_llm_client().chat_complete_stream(
        prompt, temperature=temperature, max_tokens=max_tokens, system=system
    ):
        yield delta
