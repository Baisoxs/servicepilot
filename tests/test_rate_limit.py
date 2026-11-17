"""按用户限流：超限返回 429，且不影响其他用户。"""

from types import SimpleNamespace

from fastapi.testclient import TestClient
from redis import Redis

from apps.api import deps
from apps.api.routers import chat


def _enable_rate_limit(monkeypatch, *, limit: int, window_s: int = 60) -> None:
    """把限流配置临时改小，并让 LLM 返回一个假响应（不花钱、不联网）。"""

    async def fast_stream(prompt: str, **kwargs):
        yield "ok"

    monkeypatch.setattr(chat, "astream", fast_stream)
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(
            rate_limit_chat_limit=limit,
            rate_limit_chat_window_s=window_s,
        ),
    )


def _conversation(client: TestClient, headers: dict[str, str]) -> str:
    resp = client.post("/v1/conversations", json={"title": "限流测试"}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _chat(client: TestClient, headers: dict[str, str], conversation_id: str):
    return client.post(
        "/v1/chat",
        json={"conversation_id": conversation_id, "message": "hi"},
        headers=headers,
    )


def test_chat_rate_limit_returns_429(
    client: TestClient,
    make_auth,
    redis_client: Redis,
    monkeypatch,
) -> None:
    _enable_rate_limit(monkeypatch, limit=2)

    headers = make_auth()
    user_id = client.get("/v1/auth/me", headers=headers).json()["id"]
    conversation_id = _conversation(client, headers)

    # 前 2 次在额度内
    for _ in range(2):
        assert _chat(client, headers, conversation_id).status_code == 200

    # 第 3 次超限
    too_many = _chat(client, headers, conversation_id)
    assert too_many.status_code == 429
    assert too_many.json()["code"] == "RATE_LIMITED"
    assert too_many.json()["detail"]["retry_after_s"] >= 1
    assert int(too_many.headers["Retry-After"]) >= 1

    redis_client.delete(f"sp:rl:chat:{user_id}")


def test_rate_limit_is_per_user(
    client: TestClient,
    make_auth,
    redis_client: Redis,
    monkeypatch,
) -> None:
    """一个人被打满，不该影响另一个人。"""
    _enable_rate_limit(monkeypatch, limit=1)

    alice = make_auth()
    bob = make_auth()
    alice_id = client.get("/v1/auth/me", headers=alice).json()["id"]
    bob_id = client.get("/v1/auth/me", headers=bob).json()["id"]
    alice_conversation = _conversation(client, alice)
    bob_conversation = _conversation(client, bob)

    # Alice 用掉唯一的名额
    assert _chat(client, alice, alice_conversation).status_code == 200
    assert _chat(client, alice, alice_conversation).status_code == 429

    # Bob 有自己的一块白板，不受 Alice 影响
    assert _chat(client, bob, bob_conversation).status_code == 200

    redis_client.delete(f"sp:rl:chat:{alice_id}", f"sp:rl:chat:{bob_id}")