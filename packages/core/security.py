"""密码哈希与 JWT：注册、登录、鉴权共用的安全工具。

密码：数据库里只存 Argon2id 哈希，永远不存明文，也不能“解密”回明文。
JWT：服务器签过名的通行证，客户端每次放在 Authorization: Bearer 里。
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from starlette.concurrency import run_in_threadpool

from packages.core.config import get_settings

# Argon2id：故意慢、每个密码自动加随机盐
_password_hash = PasswordHash.recommended()

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    """把明文密码变成 Argon2 哈希。注册时用。"""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码和数据库里的哈希是否匹配。登录时用。"""
    return _password_hash.verify(password, password_hash)


async def hash_password_async(password: str) -> str:
    """异步版本：Argon2 很吃 CPU，放线程池，别卡住事件循环。"""
    return await run_in_threadpool(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    """异步版本：校验密码同样放线程池。"""
    return await run_in_threadpool(verify_password, password, password_hash)


def _create_token(
    user_id: UUID | str,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        # JWT 规范要求 sub 是字符串，UUID 要先转换
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: UUID | str) -> str:
    """短命令牌：调业务接口时带它。"""
    settings = get_settings()
    return _create_token(
        user_id,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: UUID | str) -> str:
    """长命令牌：只用来换新的 access token。"""
    settings = get_settings()
    return _create_token(
        user_id,
        REFRESH_TOKEN_TYPE,
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """验签 + 验 exp + 验 type，返回 payload。

    失败时抛 jwt 异常，调用方再翻译成 401：
        jwt.ExpiredSignatureError  -> 登录已过期
        jwt.InvalidTokenError      -> token 无效 / 类型不对
    """
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return payload
