"""基于 Redis 的滑动窗口限流。

比喻：门口保安手里有一块「最近 60 秒进门名单」的白板。
每来一个人，先把名单上超过 60 秒的名字擦掉，再看名单上有几个名字：
没满就添上、放行；满了就拒绝，并告诉他还要等多久。

Redis 用有序集合（ZSET）实现：
    member = 本次请求的唯一编号（同一毫秒来两个也不会互相覆盖）
    score  = 到达时间（毫秒）

为什么用 Lua？
「擦旧记录 → 数人数 → 判断 → 记录」是四步操作。分四次发给 Redis，
两个并发请求可能同时读到「还有名额」然后都放行。Lua 脚本在 Redis 里
单线程顺序执行，整段原子完成，中间插不进别的命令。
"""

from dataclasses import dataclass
from uuid import uuid4

from redis.exceptions import RedisError

from packages.core.redis import get_redis

# 返回 {1, 0} 表示放行；{0, 等待毫秒数} 表示超限
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local member = ARGV[3]

-- 用 Redis 服务端时钟，避免多台应用机器的时间不一致
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

-- 1. 擦掉滑出窗口的旧记录
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window_ms)

-- 2. 数窗口内还有几条
local count = redis.call('ZCARD', key)

if count >= limit then
    -- 3a. 满了：最早那条滑出窗口时，才会腾出一个名额
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = window_ms
    if oldest[2] then
        retry_after = math.floor(tonumber(oldest[2]) + window_ms - now)
    end
    return {0, retry_after}
end

-- 3b. 没满：记下这次请求
redis.call('ZADD', key, now, member)
-- 窗口结束后这个 key 会自动消失，防止冷用户的空集合长期占内存
redis.call('PEXPIRE', key, window_ms)
return {1, 0}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_ms: int


async def check_sliding_window(key: str, *, limit: int, window_s: int) -> RateLimitResult:
    """占用一个名额。

    Redis 出错时选择「放行」（fail-open）：
    限流是用来挡流量的，不应该因为 Redis 挂了就把所有人挡在门外。
    """
    try:
        allowed, retry_after = await get_redis().eval(
            _SLIDING_WINDOW_LUA,
            1,  # 脚本里用到的 KEYS 数量
            key,
            int(window_s * 1000),
            limit,
            uuid4().hex,
        )
    except (RedisError, OSError):
        return RateLimitResult(allowed=True, retry_after_ms=0)
    return RateLimitResult(allowed=bool(allowed), retry_after_ms=int(retry_after))
