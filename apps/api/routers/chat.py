"""聊天路由：把模型输出以 SSE 流式返回，并把对话写进数据库。

流程：
1. 校验登录 + 会话归属（失败直接 404/401，此时还没开始流）
2. 用户消息先落库
3. 边收模型输出边推给客户端
4. 流正常结束后，把完整回复存成 assistant 消息
"""

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user
from apps.api.services.messages import MessageService
from packages.core.llm import astream
from packages.db.models import MessageRole, User
from packages.db.session import get_session

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "conversation_id": "0b6f7c1e-2d3a-4b5c-9d8e-1f2a3b4c5d6e",
                    "message": "我的密码重置链接失效了",
                }
            ]
        }
    )

    conversation_id: UUID
    message: str = Field(min_length=1, max_length=4000, examples=["我的密码重置链接失效了"])


async def _stream_reply(
    session: AsyncSession,
    conversation_id: UUID,
    prompt: str,
) -> AsyncIterator[str]:
    """把模型输出包装成 SSE，并在结束后保存助手回复。"""
    pieces: list[str] = []
    try:
        async for piece in astream(prompt):
            pieces.append(piece)
            yield f"data: {json.dumps({'delta': piece}, ensure_ascii=False)}\n\n"
    except Exception as exc:
        # 出错了也要把错误推给客户端，但半截的回答不落库
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
    else:
        content = "".join(pieces)
        if content:
            await MessageService(session).add_reply(conversation_id, content)
    yield "data: [DONE]\n\n"


@router.post(
    "/v1/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE 流：每个 data 帧是一个 JSON，最后以 [DONE] 结束",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": (
                        'data: {"delta": "您好"}\n\n'
                        'data: {"delta": "，我来帮您处理"}\n\n'
                        "data: [DONE]\n\n"
                    ),
                }
            },
        }
    },
)
async def chat_endpoint(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    # 先落用户消息：这一步同时校验了会话属于当前用户
    await MessageService(session).create(
        current_user.id,
        req.conversation_id,
        role=MessageRole.user,
        content=req.message,
    )
    return StreamingResponse(
        _stream_reply(session, req.conversation_id, req.message),
        media_type="text/event-stream",
    )
