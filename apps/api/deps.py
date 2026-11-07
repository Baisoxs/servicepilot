"""FastAPI 共享依赖（dependency）。

依赖 = “这个接口开始处理之前，框架先帮我准备好的东西”。
get_current_user 从 Authorization 头里取 token，验签，再把用户对象交出来。
"""

from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.errors import UnauthorizedError
from apps.api.repositories.users import UserRepository
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
