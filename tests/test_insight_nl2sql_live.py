"""端到端 NL2SQL 真实评测（私有化 LLM 实证）—— 接**本地 Ollama**跑真模型。

把 `app.evaluation.insight_eval.end_to_end_sql_accuracy`（此前只用 replay stub 验证打分逻辑）
接到**真实** `app.agents.data_insight.nl2sql.generate_sql`（LLM 直出 SQL），用本地 Ollama 跑
`qwen2.5:3b-instruct`，对 `GOLD_SQL_GEN_CASES` 固化端到端准确率下限。

这条同时实证两件事（W09「私有化 LLM」目标）：
1. **私有路径通**：NutriCore 的 `chat_complete` → 本地 Ollama（OpenAI 兼容）→ 真实生成（smoke）。
2. **端到端 SQL 生成质量**：真实模型直出的 SQL 过安全 gate ∧ 命中期望表/列的比例。

- **不在 CI allowlist**：依赖本地 Ollama + 已 pull 模型；靠 `pytestmark` 在不可用时自动 skip。
- 显式打 Ollama（不读 .env 的云后端），故验证的是「私有化」路径本身、可在无显卡开发机复现。
- 跑法：`ollama pull qwen2.5:3b-instruct` 后 `pytest tests/test_insight_nl2sql_live.py -v`。
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.request

import pytest

_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
_OLLAMA_MODEL = os.getenv("OLLAMA_EVAL_MODEL", "qwen2.5:3b-instruct")


def _ollama_ready() -> bool:
    """本地 Ollama 在线且目标模型已 pull 才跑，否则 skip（不误红）。"""
    try:
        with urllib.request.urlopen(f"{_OLLAMA_URL}/models", timeout=3) as r:
            ids = {m.get("id", "") for m in json.load(r).get("data", [])}
        return any(_OLLAMA_MODEL.split(":")[0] in i for i in ids)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_ready(), reason=f"需本地 Ollama + 模型 {_OLLAMA_MODEL}"
)


@pytest.fixture
def ollama_backend(monkeypatch):
    """把 LLM 配置临时指向本地 Ollama（env 优先级高于 .env），并清掉 settings/client 缓存。"""
    monkeypatch.setenv("LLM_BASE_URL", _OLLAMA_URL)
    monkeypatch.setenv("LLM_MODEL", _OLLAMA_MODEL)
    monkeypatch.setenv("LLM_API_KEY", "ollama")
    monkeypatch.setenv("LLM_TEMPERATURE", "0")

    from app.config import get_settings
    from app.core import llm

    get_settings.cache_clear()
    llm._client.cache_clear()
    yield
    get_settings.cache_clear()
    llm._client.cache_clear()


def test_chat_complete_live_ollama_smoke(ollama_backend):
    """私有路径 smoke：chat_complete → 本地 Ollama → 非空回复。"""
    from app.core.llm import chat_complete

    out = asyncio.run(chat_complete("只回复两个汉字：你好", max_tokens=32))
    assert out.strip(), "本地 Ollama 返回空"


def test_e2e_sql_accuracy_live_ollama(ollama_backend):
    """端到端：真实模型直出 SQL 的 e2e 准确率不低于下限（3b 小模型保守取 0.5）。"""
    from app.agents.data_insight.nl2sql import generate_sql
    from app.evaluation.insight_eval import GOLD_SQL_GEN_CASES, end_to_end_sql_accuracy

    def generator(question: str, user_id: str) -> str:
        return asyncio.run(generate_sql(question, user_id))

    acc = end_to_end_sql_accuracy(GOLD_SQL_GEN_CASES, generator)
    print(f"\n[live] e2e_sql_accuracy(ollama {_OLLAMA_MODEL}) = {acc:.3f}")
    assert acc >= 0.5, f"e2e_sql_accuracy(ollama {_OLLAMA_MODEL})={acc:.2f} < 0.5"
