"""会话列表的 Redis 缓存（cache-aside 模式）。

读路径：先查 Redis，命中直接返回；没命中再查数据库，并把结果写回 Redis。
写路径：先改数据库，再把该用户的「版本号」加一。

为什么不直接删缓存？
列表缓存的 key 里带分页参数（limit/offset），一个用户可能有无穷多个 key，
逐个删既慢又容易漏。所以 key 里再带一个版本号：
写操作把版本号 +1，之后所有读请求都用新版本，旧 key 交给 TTL 自然过期。
这也避开了「删缓存和并发读之间的竞态」——旧请求最多把结果写回旧版本，没人会读到。

缓存是加速层，不是依赖：Redis 出错就降级为直接查库，接口照常返回。
"""

import json
import logging
import random
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from packages.core.config import get_settings
from packages.core.redis import get_redis

logger = logging.getLogger(__name__)

# 统一前缀 sp:，方便在 redis-cli 里按前缀观察
_VERSION_KEY = "sp:conv:ver:{user_id}"
_LIST_KEY = "sp:conv:list:{user_id}:v{version}:l{limit}:o{offset}"


def _version_key(user_id: UUID) -> str:
    return _VERSION_KEY.format(user_id=user_id)


def _list_key(user_id: UUID, version: int, limit: int, offset: int) -> str:
    return _LIST_KEY.format(
        user_id=user_id,
        version=version,
        limit=limit,
        offset=offset,
    )


async def _version(redis: Redis, user_id: UUID) -> int:
    """当前版本号，没设置过就是 0。"""
    raw = await redis.get(_version_key(user_id))
    return int(raw or 0)


async def get_list(user_id: UUID, *, limit: int, offset: int) -> dict[str, Any] | None:
    """取一页会话缓存。没命中或 Redis 出错都返回 None（调用方去查库）。"""
    try:
        redis = get_redis()
        version = await _version(redis, user_id)
        raw = await redis.get(_list_key(user_id, version, limit, offset))
        if raw is None:
            return None
        return json.loads(raw)
    except (RedisError, OSError) as exc:
        logger.warning("读会话缓存失败，降级为查库：%s", exc)
        return None


async def set_list(
    user_id: UUID,
    *,
    limit: int,
    offset: int,
    items: list[dict[str, Any]],
    total: int,
) -> None:
    """把一页查询结果写进缓存。写失败只记日志，不影响主流程。"""
    try:
        redis = get_redis()
        version = await _version(redis, user_id)
        ttl = get_settings().conversation_cache_ttl_s
        # 加一点随机抖动：避免大量 key 同一秒过期，一起砸到数据库（缓存雪崩）
        ttl += random.randint(0, max(1, ttl // 5))
        payload = json.dumps({"items": items, "total": total}, ensure_ascii=False)
        await redis.set(
            _list_key(user_id, version, limit, offset),
            payload,
            ex=ttl,
        )
    except (RedisError, OSError) as exc:
        logger.warning("写会话缓存失败：%s", exc)


async def invalidate_user(user_id: UUID) -> None:
    """让这个用户的会话列表缓存整体作废（版本号 +1）。"""
    try:
        await get_redis().incr(_version_key(user_id))
    except (RedisError, OSError) as exc:
        logger.warning("失效会话缓存失败：%s", exc)
