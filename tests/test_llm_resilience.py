"""LLM 调用的并发 / 超时 / 重试测试（不连真实 API）。"""

import asyncio
import time
from types import SimpleNamespace

import pytest

from packages.core import llm


class FakeHTTPError(Exception):
    """鸭子类型的 HTTP 错误：只要有 status_code，_is_retryable 就认。"""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class FakeChunk:
    """冒充 openai 的 chunk：代码只用到 choices[0].delta.content。"""

    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(delta=SimpleNamespace(content=content))]


class FakeStream:
    """冒充 openai.AsyncStream：支持 async with 和异步迭代。"""

    def __init__(self, pieces, error_after=None) -> None:
        self._pieces = list(pieces)
        self._error_after = error_after

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for piece in self._pieces:
            yield FakeChunk(piece)
        if self._error_after is not None:
            raise self._error_after


class SlowStream(FakeStream):
    async def _iter(self):
        await asyncio.sleep(1)
        yield FakeChunk("x")


class CounterStream(FakeStream):
    """记录同时有多少个流在跑，用来验证信号量。"""

    def __init__(self, counter) -> None:
        super().__init__([])
        self._counter = counter

    async def _iter(self):
        self._counter["running"] += 1
        self._counter["peak"] = max(self._counter["peak"], self._counter["running"])
        try:
            await asyncio.sleep(0.05)
            yield FakeChunk("x")
        finally:
            self._counter["running"] -= 1


def test_is_retryable() -> None:
    assert llm._is_retryable(FakeHTTPError(429))
    assert llm._is_retryable(FakeHTTPError(500))
    assert llm._is_retryable(TimeoutError())
    assert not llm._is_retryable(FakeHTTPError(401))
    assert not llm._is_retryable(FakeHTTPError(404))
    assert not llm._is_retryable(ValueError("boom"))


def test_backoff_grows_and_caps() -> None:
    values = [llm._backoff_delay(i) for i in range(8)]
    assert all(0 <= d <= 8.0 for d in values)
    # 同一个 attempt 多取几次，值不应该完全相同（说明抖动生效）
    assert len({llm._backoff_delay(3) for _ in range(20)}) > 1


async def test_retries_before_first_piece(monkeypatch) -> None:
    calls = []

    async def fake_open(messages, temperature):
        calls.append(1)
        if len(calls) < 3:
            return FakeStream([], FakeHTTPError(429))
        return FakeStream(["o", "k"])

    monkeypatch.setattr(llm, "_open_stream", fake_open)
    monkeypatch.setattr(llm, "_backoff_delay", lambda attempt: 0.0)
    sem = asyncio.Semaphore(1)

    pieces = [p async for p in llm.astream("hi", max_retries=2, timeout_s=1, semaphore=sem)]
    assert pieces == ["o", "k"]
    assert len(calls) == 3


async def test_no_retry_after_partial_output(monkeypatch) -> None:
    calls = []

    async def fake_open(messages, temperature):
        calls.append(1)
        return FakeStream(["a"], FakeHTTPError(429))

    monkeypatch.setattr(llm, "_open_stream", fake_open)
    monkeypatch.setattr(llm, "_backoff_delay", lambda attempt: 0.0)
    sem = asyncio.Semaphore(1)

    got = []
    with pytest.raises(FakeHTTPError):
        async for p in llm.astream("hi", max_retries=2, timeout_s=1, semaphore=sem):
            got.append(p)
    assert got == ["a"]
    assert len(calls) == 1


async def test_non_retryable_error(monkeypatch) -> None:
    calls = []

    async def fake_open(messages, temperature):
        calls.append(1)
        return FakeStream([], FakeHTTPError(401))

    monkeypatch.setattr(llm, "_open_stream", fake_open)
    sem = asyncio.Semaphore(1)

    with pytest.raises(FakeHTTPError):
        async for _ in llm.astream("hi", max_retries=2, timeout_s=1, semaphore=sem):
            pass
    assert len(calls) == 1


async def test_timeout(monkeypatch) -> None:
    async def fake_open(messages, temperature):
        return SlowStream([])

    monkeypatch.setattr(llm, "_open_stream", fake_open)
    sem = asyncio.Semaphore(1)

    started = time.perf_counter()
    with pytest.raises(TimeoutError):
        async for _ in llm.astream("hi", max_retries=0, timeout_s=0.05, semaphore=sem):
            pass
    assert time.perf_counter() - started < 0.5


async def test_semaphore_limits_concurrency(monkeypatch) -> None:
    counter = {"running": 0, "peak": 0}

    async def fake_open(messages, temperature):
        return CounterStream(counter)

    monkeypatch.setattr(llm, "_open_stream", fake_open)
    sem = asyncio.Semaphore(2)

    async def one_request() -> None:
        async for _ in llm.astream("hi", max_retries=0, timeout_s=1, semaphore=sem):
            pass

    await asyncio.gather(*(one_request() for _ in range(6)))
    assert counter["peak"] == 2


async def test_consumer_breaks_early_releases_semaphore(monkeypatch) -> None:
    async def fake_open(messages, temperature):
        return FakeStream(["a", "b", "c"])

    monkeypatch.setattr(llm, "_open_stream", fake_open)
    sem = asyncio.Semaphore(1)
    agen = llm.astream("hi", max_retries=0, timeout_s=1, semaphore=sem)

    first = await anext(agen)
    assert first == "a"
    await agen.aclose()
    assert not sem.locked()


async def test_cancelled_is_not_retried(monkeypatch) -> None:
    calls = []

    async def fake_open(messages, temperature):
        calls.append(1)
        return FakeStream([], asyncio.CancelledError())

    monkeypatch.setattr(llm, "_open_stream", fake_open)
    sem = asyncio.Semaphore(1)

    with pytest.raises(asyncio.CancelledError):
        async for _ in llm.astream("hi", max_retries=2, timeout_s=1, semaphore=sem):
            pass
    assert len(calls) == 1
