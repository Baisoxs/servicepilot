"""测试进程的全局配置和共享 fixture。

Windows 上 Python 3.12 默认用 ProactorEventLoop，而 psycopg 的异步驱动
不支持它（会报 "Psycopg cannot use the 'ProactorEventLoop'"）。
Starlette 的 TestClient 在后台线程里按默认策略新建事件循环，
所以测试进程启动时统一切到 Selector。
"""

import asyncio
import sys
import uuid
from collections.abc import Callable, Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.core.config import get_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _dsn() -> str:
    """SQLAlchemy 的连接串带 +psycopg 驱动后缀，psycopg 自己连的时候要去掉。"""
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


def _db_available() -> bool:
    try:
        with psycopg.connect(_dsn(), connect_timeout=2):
            return True
    except psycopg.Error:
        return False


@pytest.fixture(scope="session")
def db_available() -> None:
    """数据库没起来时，所有依赖它的测试自动 skip，而不是报一堆连接错误。"""
    if not _db_available():
        pytest.skip("PostgreSQL 未启动（先 make up）")


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """整个测试会话共用一个 TestClient（以及它背后的事件循环）。"""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def db_conn(db_available: None) -> Iterator[psycopg.Connection]:
    """同步数据库连接，只在测试里做断言或清理用。"""
    with psycopg.connect(_dsn()) as conn:
        yield conn


@pytest.fixture
def cleanup_emails(db_available: None) -> Iterator[list[str]]:
    """测试里注册的邮箱都记在这里，结束时统一删用户。

    users 上的外键是 ON DELETE CASCADE，删用户会连带删掉他的会话。
    """
    emails: list[str] = []
    yield emails
    if emails:
        with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
            # psycopg 的 executemany 在 cursor 上，不在 connection 上
            cur.executemany(
                "DELETE FROM users WHERE email = %s",
                [(addr,) for addr in emails],
            )
            conn.commit()


@pytest.fixture
def email(cleanup_emails: list[str]) -> str:
    addr = f"test-{uuid.uuid4().hex}@example.com"
    cleanup_emails.append(addr)
    return addr


@pytest.fixture
def make_auth(client: TestClient, cleanup_emails: list[str]) -> Callable[[], dict[str, str]]:
    """注册并登录一个新用户，返回能直接放进请求头的 Authorization。"""

    def _make() -> dict[str, str]:
        addr = f"test-{uuid.uuid4().hex}@example.com"
        cleanup_emails.append(addr)

        registered = client.post(
            "/v1/auth/register",
            json={"email": addr, "password": "password123"},
        )
        assert registered.status_code == 201, registered.text

        logged_in = client.post(
            "/v1/auth/login",
            json={"email": addr, "password": "password123"},
        )
        assert logged_in.status_code == 200, logged_in.text
        return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}

    return _make
