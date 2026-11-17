"""Redis 客户端：整个进程共享一个异步连接池。

创建客户端本身很便宜（连接是惰性建立的），真正要管的是事件循环：
pytest 每个测试用例会新建一个 loop，而连接池绑定在创建它的 loop 上，
复用旧客户端会报 "Event loop is closed"。
所以这里按 loop 缓存：换了 loop 就重建。
"""

import asyncio

from redis.asyncio import Redis

from packages.core.config import get_settings

_client: Redis | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def get_redis() -> Redis:
    """返回当前事件循环专属的 Redis 客户端（惰性创建）。"""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = Redis.from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
            # 缓存是加速层：Redis 卡住时宁可快速失败降级，也不要拖住用户请求
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        _client_loop = loop
    return _client


async def close_redis() -> None:
    """关闭连接池并清空缓存。应用关闭、测试收尾时调用。"""
    global _client, _client_loop
    if _client is not None:
        await _client.aclose()
        _client = None
        _client_loop = None


async def ping_redis() -> bool:
    """Redis 是否真的能用。返回 False 而不是抛异常，方便探针调用。"""
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False
