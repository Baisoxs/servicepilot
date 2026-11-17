"""SSE 通用工具：给流式输出加心跳。

LLM 首 token 很慢、或者工具调用期间，可能长时间没有数据。
代理和负载均衡器会认为连接空闲并断开。定时发一行 SSE 注释 `: ping`
就能保活；浏览器的 EventSource 会忽略注释行。
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress


async def with_heartbeat(
    source: AsyncIterator[str],
    interval: float,
    *,
    queue_size: int = 32,
) -> AsyncIterator[str | None]:
    """包装异步字符串流：超过 interval 秒没有新数据，就 yield None。

    约定：yield 字符串 = 源数据；yield None = 调用方该发心跳了。

    为什么用「后台任务 + 队列」，而不是 asyncio.wait_for(anext(source), ...)?
    因为 wait_for 超时会取消它等待的对象——直接包 anext 会把 LLM 流取消掉。
    后台任务负责一直读源流；消费者只等队列，超时取消的只是「等队列」这件事。
    """
    queue: asyncio.Queue[tuple[str, str | BaseException | None]] = asyncio.Queue(maxsize=queue_size)

    async def produce() -> None:
        try:
            async for piece in source:
                await queue.put(("data", piece))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await queue.put(("error", exc))
        else:
            await queue.put(("done", None))

    producer = asyncio.create_task(produce())
    try:
        while True:
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=interval)
            except TimeoutError:
                yield None
                continue
            if kind == "data":
                assert isinstance(payload, str)
                yield payload
            elif kind == "error":
                assert isinstance(payload, BaseException)
                raise payload
            else:
                break
    finally:
        producer.cancel()
        with suppress(asyncio.CancelledError):
            await producer
