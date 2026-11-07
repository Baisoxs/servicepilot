"""统一错误响应：自定义业务异常 + 全局异常处理器。

所有错误最终都长这样：

    {
      "code": "NOT_FOUND",        # 稳定的机器可读标识，前端按它分支
      "message": "会话不存在",      # 给人看的说明
      "detail": null,             # 结构化的补充信息，可为空
      "trace_id": "9f2c..."       # 本次请求的编号，用来查日志
    }

分层约定：
    service 层只管 raise AppError 的子类，不碰 HTTP；
    router 层不用 try/except，异常会冒泡到这里统一翻译成 HTTP 响应。
"""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# 响应体和响应头共用这个字段名
TRACE_ID_HEADER = "X-Trace-Id"


class AppError(Exception):
    """业务异常基类。

    子类只改 status_code 和 code，调用方只需要 raise 一句话。
    """

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        detail: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.message = message
        self.detail = detail
        self.headers = headers
        # 调 super() 是为了让异常对象保留 message，日志和调试时能看到
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"

    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__(
            message,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    detail: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """构造统一格式的错误响应。

    500 由最外层的 ServerErrorMiddleware 处理，那时 TraceIdMiddleware
    已经没法再补响应头，所以这里主动把 X-Trace-Id 写上。
    """
    trace_id = getattr(request.state, "trace_id", None)
    response_headers = dict(headers or {})
    if trace_id:
        response_headers[TRACE_ID_HEADER] = trace_id

    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "detail": jsonable_encoder(detail),
            "trace_id": trace_id,
        },
        headers=response_headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """在 main.py 里调用一次，注册所有异常处理器。

    Starlette 会按异常类的继承链查找处理器：
    精确类型 -> 父类 -> ... -> Exception，找到第一个就用。
    """

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        """我们自己 raise 的业务异常。"""
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """框架抛的 404 / 405 / 401 等 HTTPException。"""
        if isinstance(exc.detail, str):
            message, detail = exc.detail, None
        else:
            message, detail = "请求失败", exc.detail

        return _error_response(
            request,
            status_code=exc.status_code,
            code=f"HTTP_{exc.status_code}",
            message=message,
            detail=detail,
            # 例如 401 的 WWW-Authenticate、405 的 Allow，要原样保留
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic 参数校验失败，FastAPI 默认返回 422。"""
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="请求参数校验失败",
            detail=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        """兜底：没被认领的异常一律 500，不把内部细节返回给客户端。"""
        trace_id = getattr(request.state, "trace_id", None)
        # 真正的异常只进日志。trace_id 是把它和用户反馈对上的唯一线索。
        logger.exception("未处理异常 trace_id=%s", trace_id)
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="服务器内部错误",
            detail=None,
        )
