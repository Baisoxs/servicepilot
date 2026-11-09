"""数据库连接池与会话工厂。

三个概念，别混：

    engine   连接池。一个进程一个，全局复用。别在请求里新建。
    Session  一次「工作单元」，相当于一个事务的上下文。
    get_session  FastAPI 依赖，每个请求一个 Session，请求结束自动关闭。

用法（在路由里）：

    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from packages.db.session import get_session

    @router.get("/users")
    async def list_users(db: AsyncSession = Depends(get_session)):
        ...
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from packages.core.config import get_settings

_settings = get_settings()

# echo=True 会把每条 SQL 打到日志里，调试时有用，平时关掉
engine = create_async_engine(
    _settings.database_url,
    echo=False,  # SQL 回显
    pool_pre_ping=True,  # 取连接前先 ping 一下，避免拿到已被数据库断开的死连接
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 之后对象属性仍可读，不会触发额外查询
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：请求进来开 Session，请求结束自动关闭。"""
    async with SessionLocal() as session:
        # 不在这里 commit。事务边界由 service 层决定：
        # 一个业务操作 = 一个事务，做完了由 service 显式 commit。
        yield session
