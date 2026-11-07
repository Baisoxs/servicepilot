"""健康检查路由：存活探针与就绪探针。"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/healthz")
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


@router.get("/readyz")
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
