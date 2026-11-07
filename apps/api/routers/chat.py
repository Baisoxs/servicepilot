"""聊天路由：把模型输出以 SSE 流式返回。"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from packages.core.llm import astream

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


async def _sse(prompt: str) -> AsyncIterator[str]:
    """把模型输出包装成 SSE 格式。"""
    try:
        async for piece in astream(prompt):
            yield f"data: {json.dumps({'delta': piece}, ensure_ascii=False)}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/v1/chat")
async def chat_endpoint(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_sse(req.message), media_type="text/event-stream")
