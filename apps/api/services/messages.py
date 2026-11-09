"""消息业务逻辑。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.errors import NotFoundError
from apps.api.repositories.conversations import ConversationRepository
from apps.api.repositories.messages import MessageRepository
from packages.db.models import Conversation, Message, MessageRole


class MessageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.messages = MessageRepository(session)
        self.conversations = ConversationRepository(session)

    async def _conversation(self, user_id: UUID, conversation_id: UUID) -> Conversation:
        """先确认会话存在且属于当前用户，再做消息操作。

        所有消息接口都经过这一步：别人的会话和不存在的会话统一 404。
        """
        conversation = await self.conversations.get_owned(conversation_id, user_id)
        if conversation is None:
            raise NotFoundError("会话不存在")
        return conversation

    async def list(
        self,
        user_id: UUID,
        conversation_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Message], int]:
        await self._conversation(user_id, conversation_id)
        return await self.messages.list_for_conversation(
            conversation_id,
            limit=limit,
            offset=offset,
        )

    async def create(
        self,
        user_id: UUID,
        conversation_id: UUID,
        *,
        role: MessageRole,
        content: str,
    ) -> Message:
        await self._conversation(user_id, conversation_id)
        message = await self.messages.create(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def add_reply(self, conversation_id: UUID, content: str) -> Message:
        """保存助手回复。

        调用方保证会话已经校验过归属（/v1/chat 在开始流式输出前就查过了），
        所以这里不再重复查会话。
        """
        message = await self.messages.create(
            conversation_id=conversation_id,
            role=MessageRole.assistant,
            content=content,
        )
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def delete(self, user_id: UUID, conversation_id: UUID, message_id: UUID) -> None:
        await self._conversation(user_id, conversation_id)
        # 消息 id 和会话 id 必须同时匹配：拿 A 会话的消息 id 去 B 会话删，是 404
        message = await self.messages.get(message_id, conversation_id)
        if message is None:
            raise NotFoundError("消息不存在")
        await self.messages.delete(message)
        await self.session.commit()
