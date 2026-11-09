"""API 探针与聊天接口测试。"""

import uuid

from fastapi.testclient import TestClient

from apps.api import main
from apps.api.routers import chat, health

# 探针测试不需要数据库，用模块级 client 就够了
client = TestClient(main.app)


def test_healthz() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_ok(monkeypatch) -> None:
    async def fake_ok(host: str, port: int) -> bool:
        return True

    monkeypatch.setattr(health, "_tcp_ok", fake_ok)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


def test_readyz_degraded(monkeypatch) -> None:
    async def fake_fail(host: str, port: int) -> bool:
        return False

    monkeypatch.setattr(health, "_tcp_ok", fake_fail)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["ready"] is False


def test_chat_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat",
        json={"conversation_id": str(uuid.uuid4()), "message": "hi"},
    )
    assert resp.status_code == 401


def test_chat_rejects_empty(client: TestClient, make_auth) -> None:
    headers = make_auth()
    resp = client.post(
        "/v1/chat",
        json={"conversation_id": str(uuid.uuid4()), "message": ""},
        headers=headers,
    )
    assert resp.status_code == 422


def test_chat_rejects_other_users_conversation(client: TestClient, make_auth) -> None:
    alice = make_auth()
    bob = make_auth()
    conversation = client.post("/v1/conversations", json={"title": "Alice 的会话"}, headers=alice)
    assert conversation.status_code == 201

    resp = client.post(
        "/v1/chat",
        json={"conversation_id": conversation.json()["id"], "message": "插一句"},
        headers=bob,
    )
    assert resp.status_code == 404


def test_chat_stream(client: TestClient, make_auth, monkeypatch) -> None:
    async def fake_stream(prompt: str, system: str | None = None, temperature: float = 0.2):
        for piece in ["你", "好"]:
            yield piece

    monkeypatch.setattr(chat, "astream", fake_stream)
    headers = make_auth()
    conversation = client.post("/v1/conversations", json={"title": "聊天"}, headers=headers)
    conversation_id = conversation.json()["id"]

    with client.stream(
        "POST",
        "/v1/chat",
        json={"conversation_id": conversation_id, "message": "hi"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert '"delta": "你"' in body
    assert '"delta": "好"' in body
    assert "data: [DONE]" in body

    # 用户消息和助手回复都已经落库，按时间正序
    listed = client.get(f"/v1/conversations/{conversation_id}/messages", headers=headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["role"] for item in items] == ["user", "assistant"]
    assert items[0]["content"] == "hi"
    assert items[1]["content"] == "你好"
