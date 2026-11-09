"""conversations 表的仓库层：只负责数据库读写。"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.models import Conversation


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Conversation], int]:
        """查某个用户的会话，返回 (当前页, 总条数)。

        软删除的会话（deleted_at 不为空）不参与查询和计数。
        """
        conditions = (
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
        stmt = (
            select(Conversation)
            .where(*conditions)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Conversation).where(*conditions)

        items = list((await self.session.scalars(stmt)).all())
        total = await self.session.scalar(count_stmt) or 0
        return items, total

    async def get_owned(self, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        """按 id 查会话，但必须属于这个用户且未删除。

        别人的会话和不存在的会话都返回 None，外面统一报 404——
        这样不会泄露“这个 id 到底存不存在”。
        """
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
        return await self.session.scalar(stmt)

    async def create(self, *, user_id: UUID, title: str) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def soft_delete(self, conversation: Conversation) -> None:
        """软删除：只打时间标记，行仍然留在数据库里。"""
        conversation.deleted_at = datetime.now(UTC)
        await self.session.flush()
