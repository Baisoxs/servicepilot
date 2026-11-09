"""会话内消息接口。

路径嵌在会话下面：/v1/conversations/{conversation_id}/messages。
每个请求都先校验会话归属，所以这里不需要再单独判一次用户。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user
from apps.api.schemas.common import Page
from apps.api.schemas.message import MessageCreate, MessageOut
from apps.api.services.messages import MessageService
from packages.db.models import Message, User
from packages.db.session import get_session

router = APIRouter(
    prefix="/v1/conversations/{conversation_id}/messages",
    tags=["messages"],
)


@router.get("", response_model=Page[MessageOut])
async def list_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[MessageOut]:
    """分页列出会话里的消息，按时间正序（最早的在前面）。"""
    items, total = await MessageService(session).list(
        current_user.id,
        conversation_id,
        limit=limit,
        offset=offset,
    )
    return Page[MessageOut](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def create_message(
    conversation_id: UUID,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Message:
    """往会话里追加一条消息，默认是用户说的话。"""
    return await MessageService(session).create(
        current_user.id,
        conversation_id,
        role=body.role,
        content=body.content,
    )


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """删除一条消息（messages 没有软删除，直接删行）。"""
    await MessageService(session).delete(current_user.id, conversation_id, message_id)
