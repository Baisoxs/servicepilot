"""健康检查路由：存活探针与就绪探针。"""

import asyncio
from urllib.parse import urlparse

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from packages.core.config import get_settings

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


def _host_port(url: str, default_port: int) -> tuple[str, int]:
    """从 DATABASE_URL / REDIS_URL 里取出 host 和 port。"""
    parsed = urlparse(url)
    return parsed.hostname or "127.0.0.1", parsed.port or default_port


@router.get("/readyz")
async def readyz() -> JSONResponse:
    """就绪探针：依赖都连得上才算就绪；地址从配置读，容器内也能用。"""
    settings = get_settings()

    db_host, db_port = _host_port(settings.database_url, 5432)
    redis_host, redis_port = _host_port(settings.redis_url, 6379)
    # minio_endpoint 的格式是 "host:port"，没有 scheme
    minio_host, _, minio_port = settings.minio_endpoint.partition(":")

    checks = {
        "postgres": await _tcp_ok(db_host, db_port),
        "redis": await _tcp_ok(redis_host, redis_port),
        "minio": await _tcp_ok(minio_host, int(minio_port or 9000)),
    }
    ok = all(checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"ready": ok, "checks": checks},
    )
