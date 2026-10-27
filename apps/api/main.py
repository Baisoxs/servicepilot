"""ServicePilot API 入口。"""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from packages.core.llm import astream

app = FastAPI(title="ServicePilot API", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """存活探针：进程能响应就算健康。"""
    return {"status": "ok"}


async def _tcp_ok(host: str, port: int) -> bool:
    """能建立 TCP 连接就算通（浅检查，不验证账号密码）。"""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1)
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, TimeoutError):
        return False


@app.get("/readyz")
async def readyz() -> JSONResponse:
    """就绪探针：依赖都连得上才算就绪。"""
    checks = {
        "postgres": await _tcp_ok("127.0.0.1", 5432),
        "redis": await _tcp_ok("127.0.0.1", 6379),
        "minio": await _tcp_ok("127.0.0.1", 9000),
    }
    ok = all(checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"ready": ok, "checks": checks},
    )


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


@app.post("/v1/chat")
async def chat_endpoint(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_sse(req.message), media_type="text/event-stream")
