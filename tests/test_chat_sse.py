"""聊天接口的 SSE 行为：心跳、错误帧、失败不落库。"""

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from apps.api.routers import chat


def test_chat_stream_emits_heartbeat(client: TestClient, make_auth, monkeypatch) -> None:
    async def slow_stream(prompt: str, **kwargs):
        yield "你"
        await asyncio.sleep(0.1)
        yield "好"

    monkeypatch.setattr(chat, "astream", slow_stream)
    monkeypatch.setattr(chat, "get_settings", lambda: SimpleNamespace(sse_heartbeat_s=0.02))

    headers = make_auth()
    conversation = client.post("/v1/conversations", json={"title": "心跳"}, headers=headers)
    conversation_id = conversation.json()["id"]

    with client.stream(
        "POST",
        "/v1/chat",
        json={"conversation_id": conversation_id, "message": "hi"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert ": ping" in body
    assert '"delta": "你"' in body
    assert '"delta": "好"' in body
    assert "data: [DONE]" in body


def test_chat_stream_error_frame_and_no_partial_save(
    client: TestClient, make_auth, monkeypatch
) -> None:
    async def broken_stream(prompt: str, **kwargs):
        yield "半"
        raise RuntimeError("模型炸了")

    monkeypatch.setattr(chat, "astream", broken_stream)
    monkeypatch.setattr(chat, "get_settings", lambda: SimpleNamespace(sse_heartbeat_s=1))

    headers = make_auth()
    conversation = client.post("/v1/conversations", json={"title": "报错"}, headers=headers)
    conversation_id = conversation.json()["id"]

    with client.stream(
        "POST",
        "/v1/chat",
        json={"conversation_id": conversation_id, "message": "hi"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert '"delta": "半"' in body
    assert '"error": "模型炸了"' in body
    assert "data: [DONE]" in body

    # 半截的回答不应该落库，只应有用户那条消息
    listed = client.get(f"/v1/conversations/{conversation_id}/messages", headers=headers)
    assert listed.status_code == 200
    assert [item["role"] for item in listed.json()["items"]] == ["user"]
