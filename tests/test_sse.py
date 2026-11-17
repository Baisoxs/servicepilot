"""SSE 心跳包装器的单元测试。"""

import asyncio

import pytest

from packages.core.sse import with_heartbeat


async def test_heartbeat_fills_idle_gap() -> None:
    async def source():
        yield "a"
        await asyncio.sleep(0.2)
        yield "b"

    items = [item async for item in with_heartbeat(source(), 0.05)]

    assert items[0] == "a"
    assert items[-1] == "b"
    assert None in items
    assert items.index("a") < items.index(None) < items.index("b")


async def test_heartbeat_propagates_source_error() -> None:
    async def source():
        yield "a"
        raise RuntimeError("boom")

    got = []
    with pytest.raises(RuntimeError, match="boom"):
        async for item in with_heartbeat(source(), 1):
            got.append(item)
    assert got == ["a"]


async def test_heartbeat_closes_source_when_consumer_stops() -> None:
    closed = asyncio.Event()

    async def source():
        try:
            while True:
                yield "x"
                await asyncio.sleep(0.01)
        finally:
            closed.set()

    agen = with_heartbeat(source(), 1)
    assert await anext(agen) == "x"
    await agen.aclose()
    assert closed.is_set()


async def test_no_heartbeat_when_data_is_fast() -> None:
    async def source():
        for piece in ["a", "b", "c"]:
            yield piece

    items = [item async for item in with_heartbeat(source(), 1)]
    assert items == ["a", "b", "c"]
