"""认证业务逻辑。

service 层负责：
    - 业务规则（邮箱不能重复、密码必须匹配）
    - 事务边界（一个业务操作 = 一次 commit）
    - 失败时 raise AppError 子类，交给全局异常处理器翻译成 HTTP
它不碰状态码、不碰 Request/Response。
"""

from uuid import UUID

import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.errors import ConflictError, UnauthorizedError
from apps.api.repositories.users import UserRepository
from packages.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password_async,
    verify_password_async,
)
from packages.db.models import User


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def register(self, email: str, password: str) -> User:
        """注册：查重 -> 哈希 -> 入库 -> 提交。"""
        email = email.strip().lower()

        if await self.users.get_by_email(email) is not None:
            raise ConflictError("邮箱已被注册")

        password_hash = await hash_password_async(password)
        try:
            user = await self.users.create(email=email, password_hash=password_hash)
            await self.session.commit()
        except IntegrityError as exc:
            # 两个请求同时注册同一个邮箱时，查重都会通过，
            # 最后靠数据库的 unique 约束兜底。
            await self.session.rollback()
            raise ConflictError("邮箱已被注册") from exc

        # created_at 由数据库生成（server_default），刷新一次把它读回来。
        await self.session.refresh(user)
        return user

    async def login(self, email: str, password: str) -> tuple[str, str]:
        """登录：校验密码，成功返回 (access, refresh)。"""
        user = await self.users.get_by_email(email)

        # 用户不存在和密码错误返回同一句话，避免暴露哪些邮箱注册过。
        if user is None or not await verify_password_async(password, user.password_hash):
            raise UnauthorizedError("邮箱或密码错误")

        return self._issue_tokens(user.id)

    async def refresh(self, refresh_token: str) -> tuple[str, str]:
        """用 refresh token 换一对新 token。"""
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedError("登录已过期，请重新登录") from exc
        except jwt.InvalidTokenError as exc:
            raise UnauthorizedError("登录凭证无效") from exc

        user = await self.users.get_by_id(self._parse_user_id(payload.get("sub")))
        if user is None:
            # token 本身有效，但用户已被删除
            raise UnauthorizedError("登录凭证无效")

        return self._issue_tokens(user.id)

    @staticmethod
    def _issue_tokens(user_id: UUID) -> tuple[str, str]:
        return create_access_token(user_id), create_refresh_token(user_id)

    @staticmethod
    def _parse_user_id(sub: object) -> UUID:
        """JWT 规范要求 sub 是字符串，这里转回 UUID。"""
        try:
            return UUID(str(sub))
        except (ValueError, TypeError) as exc:
            raise UnauthorizedError("登录凭证无效") from exc
