"""conversations CRUD 的集成测试。

需要 PostgreSQL 在跑：conftest 里的 db_available fixture 会统一处理 skip。
"""

import uuid

import psycopg
from fastapi.testclient import TestClient


def _create(client: TestClient, headers: dict[str, str], title: str = "测试会话") -> dict:
    resp = client.post("/v1/conversations", json={"title": title}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_get(client: TestClient, make_auth) -> None:
    headers = make_auth()

    created = _create(client, headers)
    assert created["title"] == "测试会话"
    assert created["created_at"]
    assert created["updated_at"]

    resp = client.get(f"/v1/conversations/{created['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_pagination(client: TestClient, make_auth) -> None:
    headers = make_auth()
    for index in range(3):
        _create(client, headers, title=f"会话 {index}")

    first = client.get(
        "/v1/conversations",
        params={"limit": 2, "offset": 0},
        headers=headers,
    )
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2

    second = client.get(
        "/v1/conversations",
        params={"limit": 2, "offset": 2},
        headers=headers,
    )
    assert len(second.json()["items"]) == 1


def test_users_are_isolated(client: TestClient, make_auth) -> None:
    alice = make_auth()
    bob = make_auth()
    conversation = _create(client, alice, title="Alice 的会话")

    # Bob 看不到 Alice 的会话
    assert client.get("/v1/conversations", headers=bob).json()["total"] == 0
    assert client.get(f"/v1/conversations/{conversation['id']}", headers=bob).status_code == 404
    assert (
        client.patch(
            f"/v1/conversations/{conversation['id']}",
            json={"title": "抢走"},
            headers=bob,
        ).status_code
        == 404
    )
    assert client.delete(f"/v1/conversations/{conversation['id']}", headers=bob).status_code == 404

    # Alice 自己的还在
    assert client.get(f"/v1/conversations/{conversation['id']}", headers=alice).status_code == 200


def test_rename(client: TestClient, make_auth) -> None:
    headers = make_auth()
    conversation = _create(client, headers)

    resp = client.patch(
        f"/v1/conversations/{conversation['id']}",
        json={"title": "  新标题  "},
        headers=headers,
    )
    assert resp.status_code == 200
    # StringConstraints 会去掉首尾空格
    assert resp.json()["title"] == "新标题"


def test_soft_delete_hides_row_but_keeps_it(
    client: TestClient,
    make_auth,
    db_conn: psycopg.Connection,
) -> None:
    headers = make_auth()
    conversation = _create(client, headers)

    resp = client.delete(f"/v1/conversations/{conversation['id']}", headers=headers)
    assert resp.status_code == 204
    assert resp.content == b""

    # 对外看不见了
    assert client.get(f"/v1/conversations/{conversation['id']}", headers=headers).status_code == 404
    assert client.get("/v1/conversations", headers=headers).json()["total"] == 0

    # 但数据库里的行还在，只是 deleted_at 有值——这就是软删除
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT deleted_at FROM conversations WHERE id = %s",
            (uuid.UUID(conversation["id"]),),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] is not None


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/v1/conversations").status_code == 401
    assert client.post("/v1/conversations", json={"title": "x"}).status_code == 401


def test_blank_title_is_rejected(client: TestClient, make_auth) -> None:
    headers = make_auth()

    resp = client.post("/v1/conversations", json={"title": "   "}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"
