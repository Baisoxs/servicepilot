"""会话业务逻辑。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.errors import NotFoundError
from apps.api.repositories.conversations import ConversationRepository
from packages.db.models import Conversation


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)

    async def create(self, user_id: UUID, title: str) -> Conversation:
        conversation = await self.conversations.create(user_id=user_id, title=title)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def list(
        self,
        user_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Conversation], int]:
        return await self.conversations.list_for_user(
            user_id,
            limit=limit,
            offset=offset,
        )

    async def get(self, user_id: UUID, conversation_id: UUID) -> Conversation:
        conversation = await self.conversations.get_owned(conversation_id, user_id)
        if conversation is None:
            raise NotFoundError("会话不存在")
        return conversation

    async def rename(self, user_id: UUID, conversation_id: UUID, title: str) -> Conversation:
        conversation = await self.get(user_id, conversation_id)
        conversation.title = title
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def delete(self, user_id: UUID, conversation_id: UUID) -> None:
        conversation = await self.get(user_id, conversation_id)
        await self.conversations.soft_delete(conversation)
        await self.session.commit()
