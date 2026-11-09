"""会话内消息接口的集成测试。

需要 PostgreSQL 在跑：conftest 里的 db_available fixture 会统一处理 skip。
"""

import uuid

from fastapi.testclient import TestClient


def _create_conversation(
    client: TestClient,
    headers: dict[str, str],
    title: str = "测试会话",
) -> str:
    resp = client.post("/v1/conversations", json={"title": title}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _url(conversation_id: str, suffix: str = "") -> str:
    return f"/v1/conversations/{conversation_id}/messages{suffix}"


def _append(
    client: TestClient,
    headers: dict[str, str],
    conversation_id: str,
    content: str,
    role: str | None = None,
) -> dict:
    body: dict[str, str] = {"content": content}
    if role is not None:
        body["role"] = role
    resp = client.post(_url(conversation_id), json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_append_and_list(client: TestClient, make_auth) -> None:
    headers = make_auth()
    conversation_id = _create_conversation(client, headers)

    first = _append(client, headers, conversation_id, "  我的密码重置链接失效了  ")
    second = _append(client, headers, conversation_id, "我先帮您确认一下", role="assistant")

    # 正文首尾空格被清掉，默认角色是 user
    assert first["content"] == "我的密码重置链接失效了"
    assert first["role"] == "user"
    assert second["role"] == "assistant"
    assert first["conversation_id"] == conversation_id

    resp = client.get(_url(conversation_id), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    # 时间正序：先发的排在前面
    assert [item["id"] for item in body["items"]] == [first["id"], second["id"]]


def test_pagination(client: TestClient, make_auth) -> None:
    headers = make_auth()
    conversation_id = _create_conversation(client, headers)
    for index in range(3):
        _append(client, headers, conversation_id, f"消息 {index}")

    first = client.get(_url(conversation_id), params={"limit": 2, "offset": 0}, headers=headers)
    assert first.status_code == 200
    assert first.json()["total"] == 3
    assert len(first.json()["items"]) == 2

    second = client.get(_url(conversation_id), params={"limit": 2, "offset": 2}, headers=headers)
    assert len(second.json()["items"]) == 1


def test_users_are_isolated(client: TestClient, make_auth) -> None:
    alice = make_auth()
    bob = make_auth()
    conversation_id = _create_conversation(client, alice)

    # Bob 在 Alice 的会话里什么都做不了
    assert client.get(_url(conversation_id), headers=bob).status_code == 404
    assert (
        client.post(_url(conversation_id), json={"content": "插一句"}, headers=bob).status_code
        == 404
    )

    message = _append(client, alice, conversation_id, "Alice 的消息")
    deleted = client.delete(_url(conversation_id, f"/{message['id']}"), headers=bob)
    assert deleted.status_code == 404

    # Alice 自己看得到
    assert client.get(_url(conversation_id), headers=alice).json()["total"] == 1


def test_delete_message(client: TestClient, make_auth) -> None:
    headers = make_auth()
    conversation_id = _create_conversation(client, headers)
    message = _append(client, headers, conversation_id, "待删除")

    resp = client.delete(_url(conversation_id, f"/{message['id']}"), headers=headers)
    assert resp.status_code == 204
    assert resp.content == b""

    assert client.get(_url(conversation_id), headers=headers).json()["total"] == 0


def test_message_must_belong_to_conversation(client: TestClient, make_auth) -> None:
    headers = make_auth()
    first = _create_conversation(client, headers, title="会话 A")
    second = _create_conversation(client, headers, title="会话 B")
    message = _append(client, headers, first, "只属于 A")

    # 拿 A 的消息 id 从 B 的路径删：消息 id 和会话 id 必须同时匹配
    resp = client.delete(_url(second, f"/{message['id']}"), headers=headers)
    assert resp.status_code == 404


def test_unknown_conversation_is_404(client: TestClient, make_auth) -> None:
    headers = make_auth()
    missing = str(uuid.uuid4())

    assert client.get(_url(missing), headers=headers).status_code == 404

    created = client.post(_url(missing), json={"content": "hello"}, headers=headers)
    assert created.status_code == 404


def test_requires_auth(client: TestClient) -> None:
    conversation_id = str(uuid.uuid4())
    assert client.get(_url(conversation_id)).status_code == 401
    assert client.post(_url(conversation_id), json={"content": "x"}).status_code == 401


def test_blank_content_is_rejected(client: TestClient, make_auth) -> None:
    headers = make_auth()
    conversation_id = _create_conversation(client, headers)

    resp = client.post(_url(conversation_id), json={"content": "   "}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"
