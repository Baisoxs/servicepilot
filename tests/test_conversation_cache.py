"""会话列表缓存的集成测试。

需要 PostgreSQL + Redis 都在跑（make up）。任一不可用就整组 skip。
"""

import uuid
from collections.abc import Iterator

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient
from redis import Redis

from apps.api.services import conversation_cache
from packages.core.config import get_settings


def _redis_up() -> bool:
    try:
        client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        client.ping()
        client.close()
        return True
    except redis.RedisError:
        return False


@pytest.fixture(scope="session")
def redis_available() -> None:
    if not _redis_up():
        pytest.skip("Redis 未启动（先 make up）")


@pytest.fixture
def redis_client(redis_available: None) -> Iterator[Redis]:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    yield client
    client.close()


@pytest.fixture
def cache_keys(redis_client: Redis) -> Iterator[list[str]]:
    """测试里碰过的 Redis key，结束时统一删掉，别污染本机数据。"""
    keys: list[str] = []
    yield keys
    if keys:
        redis_client.delete(*keys)


def _create(client: TestClient, headers: dict[str, str], title: str = "缓存测试") -> dict:
    resp = client.post("/v1/conversations", json={"title": title}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _user_id(client: TestClient, headers: dict[str, str]) -> str:
    resp = client.get("/v1/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _version_key(user_id: str) -> str:
    return f"sp:conv:ver:{user_id}"


def _first_title(client: TestClient, headers: dict[str, str]) -> str:
    body = client.get("/v1/conversations", headers=headers).json()
    return body["items"][0]["title"]


def test_direct_db_change_is_masked_by_cache(
    client: TestClient,
    make_auth,
    db_conn: psycopg.Connection,
    redis_client: Redis,
    cache_keys: list[str],
) -> None:
    """缓存命中时，绕过 API 直接改库，列表仍返回旧值。"""
    headers = make_auth()
    user_id = _user_id(client, headers)
    cache_keys.append(_version_key(user_id))

    conversation = _create(client, headers, title="旧标题")
    # 第一次 GET：缓存没命中，查库并把结果写回 Redis
    assert _first_title(client, headers) == "旧标题"

    # 绕过 API 直接改数据库：不经过 service，所以版本号不会 +1
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE conversations SET title = %s WHERE id = %s",
            ("新标题", uuid.UUID(conversation["id"])),
        )
    db_conn.commit()

    # 第二次 GET：命中缓存，仍然是旧标题 —— 这正是缓存生效的证据
    assert _first_title(client, headers) == "旧标题"

    # 手动把版本号 +1（相当于一次写操作），旧缓存立刻作废
    redis_client.incr(_version_key(user_id))
    assert _first_title(client, headers) == "新标题"


def test_create_invalidates_cached_empty_list(
    client: TestClient,
    make_auth,
    cache_keys: list[str],
) -> None:
    """空列表也会被缓存，所以新建后必须让它失效，否则新会话看不见。"""
    headers = make_auth()
    user_id = _user_id(client, headers)
    cache_keys.append(_version_key(user_id))

    assert client.get("/v1/conversations", headers=headers).json()["total"] == 0

    created = _create(client, headers, title="新建的会话")

    body = client.get("/v1/conversations", headers=headers).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]


def test_rename_invalidates_cache(
    client: TestClient,
    make_auth,
    cache_keys: list[str],
) -> None:
    headers = make_auth()
    user_id = _user_id(client, headers)
    cache_keys.append(_version_key(user_id))

    conversation = _create(client, headers, title="旧标题")
    assert _first_title(client, headers) == "旧标题"

    resp = client.patch(
        f"/v1/conversations/{conversation['id']}",
        json={"title": "新标题"},
        headers=headers,
    )
    assert resp.status_code == 200

    # 改名后列表立刻是新标题，而不是缓存里的旧标题
    assert _first_title(client, headers) == "新标题"


def test_delete_invalidates_cache(
    client: TestClient,
    make_auth,
    cache_keys: list[str],
) -> None:
    headers = make_auth()
    user_id = _user_id(client, headers)
    cache_keys.append(_version_key(user_id))

    conversation = _create(client, headers, title="待删除")
    assert client.get("/v1/conversations", headers=headers).json()["total"] == 1

    assert client.delete(f"/v1/conversations/{conversation['id']}", headers=headers).status_code == 204

    # 删完列表立刻变成空，不会还显示缓存中的那一条
    assert client.get("/v1/conversations", headers=headers).json()["total"] == 0


def test_redis_failure_degrades_to_database(
    client: TestClient,
    make_auth,
    monkeypatch: pytest.MonkeyPatch,
    cache_keys: list[str],
) -> None:
    """Redis 挂了，列表接口也必须能正常返回（缓存只是加速层）。"""
    headers = make_auth()
    user_id = _user_id(client, headers)
    cache_keys.append(_version_key(user_id))

    conversation = _create(client, headers, title="没有 Redis 也能用")

    def _boom() -> None:
        raise redis.ConnectionError("redis is down")

    monkeypatch.setattr(conversation_cache, "get_redis", _boom)

    resp = client.get("/v1/conversations", headers=headers)
    assert resp.status_code == 200
    assert [item["id"] for item in resp.json()["items"]] == [conversation["id"]]
