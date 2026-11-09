"""ServicePilot API 入口：只负责组装应用。"""

from fastapi import FastAPI

from apps.api.errors import register_exception_handlers
from apps.api.middleware import TraceIdMiddleware
from apps.api.routers import auth, chat, conversations, health, messages


def create_app() -> FastAPI:
    """创建一个 FastAPI 实例。

    路由注册、中间件、异常处理器都集中放在这里，
    方便测试时按需组装不同的实例。
    """
    app = FastAPI(title="ServicePilot API", version="0.1.0")

    # trace_id 要在请求进入路由前生成，错误处理器才能把它写进错误体
    app.add_middleware(TraceIdMiddleware)
    # 所有异常在这里统一翻译成 {code, message, detail, trace_id}
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(auth.router)
    app.include_router(conversations.router)
    app.include_router(messages.router)
    return app


# uvicorn 的入口是 apps.api.main:app，模块里必须有一个 app 对象
app = create_app()
