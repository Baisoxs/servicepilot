"""users 表的仓库层（repository）：只负责数据库读写。

这里没有任何业务判断：
    “邮箱重复要报 409”是业务规则，放在 service；
    这里只负责把数据取出来、存进去。
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.models import User


class UserRepository:
    """所有 users 表查询都从这里进出，SQL 不散落在 service 里。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        """按邮箱查未删除的用户。

        邮箱统一转小写：PostgreSQL 的 unique 约束区分大小写，
        不转的话 A@x.com 和 a@x.com 会变成两个账号。
        """
        stmt = select(User).where(
            User.email == email.strip().lower(),
            User.deleted_at.is_(None),
        )
        return await self.session.scalar(stmt)

    async def get_by_id(self, user_id: UUID) -> User | None:
        """按 id 查未删除的用户。"""
        stmt = select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
        return await self.session.scalar(stmt)

    async def create(self, *, email: str, password_hash: str) -> User:
        """新建用户并 flush。

        flush 只是把 INSERT 发给数据库做约束检查、拿到 id；
        真正的 commit（拍板生效）由 service 决定。
        """
        user = User(email=email.strip().lower(), password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        return user
