"""messages 表的仓库层：只负责数据库读写。"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.models import Message, MessageRole


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_conversation(
        self,
        conversation_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Message], int]:
        """查某个会话的消息，按时间正序，返回 (当前页, 总条数)。"""
        conditions = (Message.conversation_id == conversation_id,)
        stmt = (
            select(Message)
            .where(*conditions)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Message).where(*conditions)

        items = list((await self.session.scalars(stmt)).all())
        total = await self.session.scalar(count_stmt) or 0
        return items, total

    async def create(
        self,
        *,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
    ) -> Message:
        message = Message(conversation_id=conversation_id, role=role, content=content)
        self.session.add(message)
        await self.session.flush()
        return message

    async def get(self, message_id: UUID, conversation_id: UUID) -> Message | None:
        """按消息 id + 所属会话查一条消息，两个条件必须同时匹配。"""
        stmt = select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation_id,
        )
        return await self.session.scalar(stmt)

    async def delete(self, message: Message) -> None:
        await self.session.delete(message)
        await self.session.flush()
