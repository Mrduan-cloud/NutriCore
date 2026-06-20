"""多 LLM 适配层单测 —— 协议 / provider 工厂 / 请求映射 / 双 provider SDK-shell。

分两层(沿用仓库「纯解析函数离线可单测 + SDK 边界用 fake 注入」范式):
- **纯函数**(消息构造 / system 拆分 / Anthropic 请求映射 / 文本抽取 / 工厂选档):
  无任何 LLM SDK 依赖,CI 必跑。
- **SDK-shell**(用 fake AsyncOpenAI / AsyncAnthropic 注入,验证 chat_complete /
  stream 的编排+重试+映射):OpenAI 档随 openai 装即跑;Anthropic 档用
  importorskip 守——CI 装了 anthropic 会跑,裸轻量环境跳过(诚实标注)。

不触网、不起真实 LLM。Anthropic **真 live** 验证按 W09 范式延后(无 key、诚实
标注未实证);OpenAI 兼容档的 live 验证走本地 Ollama(见 DEPLOYMENT)。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core import llm


@pytest.fixture(autouse=True)
def _reset_factory():
    llm.reset_llm_client()
    yield
    llm.reset_llm_client()


# ============================ 纯函数 ============================


def test_build_messages_str_prepends_system():
    assert llm._build_messages("hi", "SYS") == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hi"},
    ]


def test_build_messages_str_without_system():
    assert llm._build_messages("hi", None) == [{"role": "user", "content": "hi"}]


def test_build_messages_list_passthrough_ignores_system_kwarg():
    """list 形式 prompt 视为已成型 messages,忽略 system kwarg(与旧行为一致)。"""
    msgs = [{"role": "user", "content": "u"}]
    assert llm._build_messages(msgs, "SYS") == msgs


def test_split_system_str():
    sys_str, msgs = llm._split_system("hi", "SYS")
    assert sys_str == "SYS"
    assert msgs == [{"role": "user", "content": "hi"}]


def test_split_system_extracts_system_from_list():
    """Anthropic:list 里的 role=system 条目须抽到顶层,messages 只留 user/assistant。"""
    prompt = [
        {"role": "system", "content": "S1"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
    ]
    sys_str, msgs = llm._split_system(prompt, "S0")
    assert sys_str == "S0\n\nS1"  # kwarg system 在前,消息里的 system 拼后
    assert msgs == [
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
    ]
    assert all(m["role"] != "system" for m in msgs)


def test_split_system_all_system_list_degrades_to_user():
    """退化:list 仅含 system → messages 不能为空,降级成一条 user 消息(内容不丢)。"""
    sys_str, msgs = llm._split_system([{"role": "system", "content": "S"}], None)
    assert sys_str is None
    assert msgs == [{"role": "user", "content": "S"}]


def test_to_anthropic_request_shape_and_no_temperature():
    req = llm._to_anthropic_request(
        "hi", system="SYS", response_format=None, max_tokens=None,
        model="claude-opus-4-8", default_max_tokens=4096,
    )
    assert req["model"] == "claude-opus-4-8"
    assert req["system"] == "SYS"
    assert req["max_tokens"] == 4096  # 未指定 → 用默认
    assert req["messages"] == [{"role": "user", "content": "hi"}]
    assert "temperature" not in req  # 现代 Claude 拒绝,适配层不透传


def test_to_anthropic_request_json_mode_injects_instruction():
    req = llm._to_anthropic_request(
        "hi", system="SYS", response_format="json", max_tokens=512,
        model="m", default_max_tokens=4096,
    )
    assert req["max_tokens"] == 512  # 显式指定优先
    assert llm._JSON_INSTRUCTION in req["system"]
    assert req["system"].startswith("SYS")


def test_to_anthropic_request_json_mode_without_system():
    req = llm._to_anthropic_request(
        "hi", system=None, response_format="json", max_tokens=None,
        model="m", default_max_tokens=4096,
    )
    assert req["system"] == llm._JSON_INSTRUCTION


def test_extract_text_objects_and_dicts_only_text():
    blocks = [
        SimpleNamespace(type="text", text="A"),
        SimpleNamespace(type="tool_use", text="IGNORED"),
        {"type": "text", "text": "B"},
        {"type": "thinking", "text": "ALSO_IGNORED"},
    ]
    assert llm._extract_text(blocks) == "AB"


def test_extract_text_empty():
    assert llm._extract_text(None) == ""
    assert llm._extract_text([]) == ""


def test_strip_code_fences_json():
    assert llm._strip_code_fences('```json\n{"ok": true}\n```') == '{"ok": true}'


def test_strip_code_fences_bare():
    assert llm._strip_code_fences("```\nplain\n```") == "plain"


def test_strip_code_fences_noop_when_unfenced():
    assert llm._strip_code_fences('{"ok": true}') == '{"ok": true}'
    # 单行只有 ``` 的退化情况不动
    assert llm._strip_code_fences("```") == "```"


# ============================ 工厂选档 ============================


def test_factory_default_is_openai_compat(monkeypatch):
    monkeypatch.setattr(llm.get_settings(), "llm_provider", "openai")
    llm.reset_llm_client()
    assert isinstance(llm.get_llm_client(), llm.OpenAICompatClient)


def test_factory_anthropic_selected(monkeypatch):
    """provider=anthropic 选 AnthropicClient——构造不 import anthropic(惰性)。"""
    monkeypatch.setattr(llm.get_settings(), "llm_provider", "anthropic")
    llm.reset_llm_client()
    assert isinstance(llm.get_llm_client(), llm.AnthropicClient)


def test_factory_unknown_falls_back_to_openai(monkeypatch):
    monkeypatch.setattr(llm.get_settings(), "llm_provider", "weird")
    llm.reset_llm_client()
    assert isinstance(llm.get_llm_client(), llm.OpenAICompatClient)


# ============================ fake SDK ============================


async def _chunk_stream(deltas):
    for d in deltas:
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=d))])


class _FakeOpenAICompletions:
    def __init__(self, captured, *, content="OPENAI_OUT", deltas=("a", "b", "c")):
        self.captured = captured
        self.content = content
        self.deltas = deltas

    async def create(self, **kwargs):
        self.captured.clear()
        self.captured.update(kwargs)
        if kwargs.get("stream"):
            return _chunk_stream(self.deltas)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class _FakeOpenAI:
    def __init__(self, captured, **kw):
        self.chat = SimpleNamespace(completions=_FakeOpenAICompletions(captured, **kw))


async def _text_stream(texts):
    for t in texts:
        yield t


class _FakeStreamCtx:
    def __init__(self, texts):
        self._texts = texts

    async def __aenter__(self):
        return SimpleNamespace(text_stream=_text_stream(self._texts))

    async def __aexit__(self, *exc):
        return False


class _FakeAnthropicMessages:
    def __init__(self, captured, *, text="CLAUDE_OUT", stream_texts=("x", "y")):
        self.captured = captured
        self.text = text
        self.stream_texts = stream_texts

    async def create(self, **req):
        self.captured.clear()
        self.captured.update(req)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])

    def stream(self, **req):
        self.captured.clear()
        self.captured.update(req)
        return _FakeStreamCtx(self.stream_texts)


class _FakeAnthropic:
    def __init__(self, captured, **kw):
        self.messages = _FakeAnthropicMessages(captured, **kw)


# ---------------- OpenAI 兼容 provider(openai 已是依赖,直接跑) ----------------


def test_openai_compat_chat_complete_returns_text_and_passes_json():
    captured: dict = {}
    client = llm.OpenAICompatClient(sdk_client=_FakeOpenAI(captured, content="HELLO"))
    out = asyncio.run(client.chat_complete("hi", response_format="json", system="S"))
    assert out == "HELLO"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][0] == {"role": "system", "content": "S"}
    assert captured["messages"][-1] == {"role": "user", "content": "hi"}


def test_openai_compat_stream_yields_deltas():
    captured: dict = {}
    client = llm.OpenAICompatClient(
        sdk_client=_FakeOpenAI(captured, deltas=("Hel", "lo"))
    )

    async def _collect():
        return [t async for t in client.chat_complete_stream("hi")]

    assert asyncio.run(_collect()) == ["Hel", "lo"]
    assert captured["stream"] is True


# ---------------- 原生 Anthropic provider(需 anthropic SDK 可导入) ----------------


def test_anthropic_chat_complete_maps_request_and_extracts_text():
    pytest.importorskip("anthropic")  # CI 装了会跑;裸轻量环境诚实跳过
    captured: dict = {}
    client = llm.AnthropicClient(sdk_client=_FakeAnthropic(captured, text="解读结果"))
    out = asyncio.run(client.chat_complete("血糖偏高", response_format="json", system="你是营养师"))
    assert out == "解读结果"
    # system 顶层、含 json 指令;max_tokens 必填;无 temperature;messages 无 system 条目
    assert captured["system"].startswith("你是营养师")
    assert llm._JSON_INSTRUCTION in captured["system"]
    assert captured["max_tokens"] == 8192  # settings.anthropic_max_tokens 默认
    assert "temperature" not in captured
    assert captured["messages"] == [{"role": "user", "content": "血糖偏高"}]


def test_anthropic_json_mode_strips_model_fences():
    """Anthropic json 模式:模型裹了 ```json 围栏时,适配层须剥成干净 JSON。"""
    pytest.importorskip("anthropic")
    captured: dict = {}
    fenced = '```json\n{"food": "燕麦"}\n```'
    client = llm.AnthropicClient(sdk_client=_FakeAnthropic(captured, text=fenced))
    out = asyncio.run(client.chat_complete("x", response_format="json"))
    assert out == '{"food": "燕麦"}'


def test_anthropic_stream_yields_text():
    pytest.importorskip("anthropic")
    captured: dict = {}
    client = llm.AnthropicClient(
        sdk_client=_FakeAnthropic(captured, stream_texts=("解", "读"))
    )

    async def _collect():
        return [t async for t in client.chat_complete_stream("hi", system="S")]

    assert asyncio.run(_collect()) == ["解", "读"]
    assert captured["system"] == "S"


# ---------------- 向后兼容公共入口委派 ----------------


def test_module_chat_complete_delegates_to_factory(monkeypatch):
    """6 个调用点用的模块级 chat_complete 须委派给当前 provider。"""
    seen: dict = {}

    class _Spy:
        async def chat_complete(self, prompt, **kw):
            seen["prompt"] = prompt
            seen["kw"] = kw
            return "DELEGATED"

    monkeypatch.setattr(llm, "get_llm_client", _Spy)
    out = asyncio.run(llm.chat_complete("hi", response_format="json"))
    assert out == "DELEGATED"
    assert seen["prompt"] == "hi"
    assert seen["kw"]["response_format"] == "json"
