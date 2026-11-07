"""会话 CRUD 接口。

所有接口都依赖 get_current_user：没登录直接 401，
并且查询永远带当前用户的 id，保证只能操作自己的会话。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user
from apps.api.schemas.common import Page
from apps.api.schemas.conversation import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
)
from apps.api.services.conversations import ConversationService
from packages.db.models import Conversation, User
from packages.db.session import get_session

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Conversation:
    """新建一个会话。"""
    return await ConversationService(session).create(current_user.id, body.title)


@router.get("", response_model=Page[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[ConversationOut]:
    """分页列出当前用户的会话，最近更新的排前面。"""
    items, total = await ConversationService(session).list(
        current_user.id,
        limit=limit,
        offset=offset,
    )
    return Page[ConversationOut](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Conversation:
    """查看单个会话。别人的会话一律 404。"""
    return await ConversationService(session).get(current_user.id, conversation_id)


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: UUID,
    body: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Conversation:
    """修改会话标题。"""
    return await ConversationService(session).rename(
        current_user.id,
        conversation_id,
        body.title,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """软删除会话：数据还在，只是不再出现在查询结果里。"""
    await ConversationService(session).delete(current_user.id, conversation_id)
