"""请求级中间件：给每个请求分配 trace_id。

trace_id 是这条请求的“快递单号”：

    响应体里返回一份，响应头里也放一份，日志里再打一份。
    用户报错时把单号给你，你就能从日志里捞出这一次请求的全部记录。
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from apps.api.errors import TRACE_ID_HEADER

# 太长的 ID 不接收，防止有人用超长请求头污染日志
_MAX_TRACE_ID_LENGTH = 64


class TraceIdMiddleware(BaseHTTPMiddleware):
    """把 trace_id 放进 request.state，并写回响应头。

    客户端如果自带 X-Trace-Id，就复用它（跨服务调用时可以串成一条链）；
    没有就生成一个新的 uuid。
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(TRACE_ID_HEADER)
        if incoming and len(incoming) <= _MAX_TRACE_ID_LENGTH:
            trace_id = incoming
        else:
            trace_id = uuid.uuid4().hex

        # 异常处理器通过 request.state.trace_id 拿到它
        request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        return response
