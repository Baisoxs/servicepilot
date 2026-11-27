"""会话业务逻辑。"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.errors import NotFoundError
from apps.api.repositories.conversations import ConversationRepository
from apps.api.schemas.conversation import ConversationOut
from apps.api.services import conversation_cache
from packages.db.models import Conversation


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)

    async def create(self, user_id: UUID, title: str) -> Conversation:
        conversation = await self.conversations.create(user_id=user_id, title=title)
        await self.session.commit()
        await self.session.refresh(conversation)
        # 列表里多了一条：让这个用户的旧缓存整体作废
        await conversation_cache.invalidate_user(user_id)
        return conversation

    async def list(
        self,
        user_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        # ① 先看便签盒：命中就直接返回，一次数据库都不查
        cached = await conversation_cache.get_list(user_id, limit=limit, offset=offset)
        if cached is not None:
            return cached["items"], cached["total"]

        # ② 没命中才查档案柜
        items, total = await self.conversations.list_for_user(
            user_id,
            limit=limit,
            offset=offset,
        )
        # ORM 对象不能直接塞进 JSON（datetime、UUID 都不是 JSON 原生类型），
        # 先转成「只含基本类型」的字典，datetime 会变成 ISO 字符串
        payload = [ConversationOut.model_validate(item).model_dump(mode="json") for item in items]
        # ③ 抄一张便签贴回 Redis
        await conversation_cache.set_list(
            user_id,
            limit=limit,
            offset=offset,
            items=payload,
            total=total,
        )
        return payload, total

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
        # 标题变了，列表里的旧数据不能再用
        await conversation_cache.invalidate_user(user_id)
        return conversation

    async def delete(self, user_id: UUID, conversation_id: UUID) -> None:
        conversation = await self.get(user_id, conversation_id)
        await self.conversations.soft_delete(conversation)
        await self.session.commit()
        # 少了一条，同样让缓存作废
        await conversation_cache.invalidate_user(user_id)
