"""FastAPI 共享依赖（dependency）。

依赖 = “这个接口开始处理之前，框架先帮我准备好的东西”。
get_current_user 从 Authorization 头里取 token，验签，再把用户对象交出来。
"""

import math
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.errors import RateLimitedError, UnauthorizedError
from apps.api.repositories.users import UserRepository
from packages.core.config import get_settings
from packages.core.rate_limit import check_sliding_window
from packages.core.security import decode_token
from packages.db.models import User
from packages.db.session import get_session

# auto_error=False：没带 Authorization 头时不让 FastAPI 自己抛 403，
# 而是返回 None，由我们统一抛 401 + 统一错误格式。
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """从 access token 解析出当前用户。需要登录的接口把它作为依赖。"""
    if credentials is None:
        raise UnauthorizedError("缺少认证信息")

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except jwt.ExpiredSignatureError as exc:
        # 注意顺序：ExpiredSignatureError 是 InvalidTokenError 的子类
        raise UnauthorizedError("登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("登录凭证无效") from exc

    try:
        user_id = UUID(str(payload.get("sub")))
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError("登录凭证无效") from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        # token 有效，但用户已不存在或已被软删除
        raise UnauthorizedError("登录凭证无效")
    return user


async def enforce_chat_rate_limit(
    current_user: User = Depends(get_current_user),
) -> None:
    """每次 /v1/chat 处理前先占一个名额；超限直接抛 429。

    key 里带用户 id：每人一块自己的白板，互不牵连。
    """
    settings = get_settings()
    result = await check_sliding_window(
        f"sp:rl:chat:{current_user.id}",
        limit=settings.rate_limit_chat_limit,
        window_s=settings.rate_limit_chat_window_s,
    )
    if not result.allowed:
        # Retry-After 按秒向上取整：客户端只需要知道「几秒后再来」
        retry_after_s = max(1, math.ceil(result.retry_after_ms / 1000))
        raise RateLimitedError(
            "请求太频繁，请稍后再试",
            retry_after_s=retry_after_s,
            detail={"retry_after_s": retry_after_s},
        )
