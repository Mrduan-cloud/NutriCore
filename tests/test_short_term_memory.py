"""短期记忆(Redis-backed)单测 —— 用内存假 Redis,完全离线。

只验证我们自己的逻辑(轮次截断 / 角色顺序 / 解析 / 异常降级),
不依赖真实 Redis;用 asyncio.run 跑协程,无需 pytest-asyncio 插件。
"""
import asyncio

import pytest

from app.agents.nutritionist import memory


class FakeRedis:
    """实现本模块用到的 list 命令子集,语义对齐 Redis(含负索引)。"""

    def __init__(self):
        self.store: dict[str, list[str]] = {}

    @staticmethod
    def _bounds(n: int, start: int, end: int) -> tuple[int, int]:
        s = start if start >= 0 else n + start
        e = end if end >= 0 else n + end
        return max(s, 0), min(e, n - 1)

    async def rpush(self, key, *vals):
        self.store.setdefault(key, []).extend(vals)
        return len(self.store[key])

    async def ltrim(self, key, start, end):
        lst = self.store.get(key, [])
        s, e = self._bounds(len(lst), start, end)
        self.store[key] = lst[s : e + 1] if s <= e else []
        return True

    async def lrange(self, key, start, end):
        lst = self.store.get(key, [])
        if not lst:
            return []
        s, e = self._bounds(len(lst), start, end)
        return lst[s : e + 1] if s <= e else []

    async def expire(self, key, ttl):
        return True

    async def delete(self, *keys):
        return sum(1 for k in keys if self.store.pop(k, None) is not None)


class BrokenRedis:
    """所有命令都抛错,用于验证降级路径。"""

    async def rpush(self, *a, **k):
        raise ConnectionError("redis down")

    async def ltrim(self, *a, **k):
        raise ConnectionError("redis down")

    async def lrange(self, *a, **k):
        raise ConnectionError("redis down")

    async def expire(self, *a, **k):
        raise ConnectionError("redis down")

    async def delete(self, *a, **k):
        raise ConnectionError("redis down")


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(memory, "get_redis", lambda: fake)
    return fake


def test_remember_then_recent_roundtrip(fake_redis):
    async def run():
        await memory.remember_turn("u", "s", "我减脂", "建议高蛋白")
        return await memory.recent_turns("u", "s")

    turns = asyncio.run(run())
    assert turns == [
        {"role": "user", "content": "我减脂"},
        {"role": "assistant", "content": "建议高蛋白"},
    ]


def test_trims_to_max_turns(fake_redis):
    async def run():
        for i in range(1, 9):  # 8 轮,超过上限 6
            await memory.remember_turn("u", "s", f"u{i}", f"a{i}")
        return await memory.recent_turns("u", "s")

    turns = asyncio.run(run())
    # 只保留最近 6 轮 = 12 条,最早两轮(u1/u2)被截断
    assert len(turns) == 12
    assert turns[0] == {"role": "user", "content": "u3"}
    assert turns[-1] == {"role": "assistant", "content": "a8"}


def test_custom_max_turns(fake_redis):
    async def run():
        for i in range(1, 5):
            await memory.remember_turn("u", "s", f"u{i}", f"a{i}", max_turns=2)
        return await memory.recent_turns("u", "s", max_turns=2)

    turns = asyncio.run(run())
    assert [t["content"] for t in turns] == ["u3", "a3", "u4", "a4"]


def test_sessions_are_isolated(fake_redis):
    async def run():
        await memory.remember_turn("u", "s1", "在s1", "回s1")
        await memory.remember_turn("u", "s2", "在s2", "回s2")
        return await memory.recent_turns("u", "s1")

    turns = asyncio.run(run())
    assert turns == [
        {"role": "user", "content": "在s1"},
        {"role": "assistant", "content": "回s1"},
    ]


def test_empty_session_returns_empty(fake_redis):
    assert asyncio.run(memory.recent_turns("u", "nope")) == []


def test_blank_turn_not_stored(fake_redis):
    async def run():
        await memory.remember_turn("u", "s", "  ", "非空")  # 用户空 → 跳过
        await memory.remember_turn("u", "s", "非空", "   ")  # 助手空 → 跳过
        return await memory.recent_turns("u", "s")

    assert asyncio.run(run()) == []


def test_clear_short_term(fake_redis):
    async def run():
        await memory.remember_turn("u", "s", "x", "y")
        await memory.clear_short_term("u", "s")
        return await memory.recent_turns("u", "s")

    assert asyncio.run(run()) == []


def test_degrades_gracefully_when_redis_down(monkeypatch):
    monkeypatch.setattr(memory, "get_redis", lambda: BrokenRedis())

    async def run():
        # 写失败不抛错;读失败返回 []
        await memory.remember_turn("u", "s", "a", "b")
        return await memory.recent_turns("u", "s")

    assert asyncio.run(run()) == []
