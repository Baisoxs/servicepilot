"""慢请求不阻塞其他请求：asyncio 并发的实测。

同时发两个 /v1/chat，每个内部都等 0.5 秒：
- await asyncio.sleep  -> 两个请求并发等待，总耗时约 0.5 秒
- time.sleep（阻塞）    -> 事件循环被占住，总耗时约 1.0 秒
"""

import asyncio
import time

import httpx
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.routers import chat


def _conversation(client: TestClient, headers: dict[str, str]) -> str:
    resp = client.post("/v1/conversations", json={"title": "并发测试"}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _chat_pair(
    payloads: list[dict],
    headers_list: list[dict[str, str]],
) -> tuple[list[int], float]:
    """同时发两个聊天请求，返回 (状态码列表, 总耗时秒数)。"""
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        started = time.perf_counter()
        responses = await asyncio.gather(
            *[
                ac.post("/v1/chat", json=payload, headers=headers)
                for payload, headers in zip(payloads, headers_list, strict=True)
            ]
        )
        elapsed = time.perf_counter() - started
    return [response.status_code for response in responses], elapsed


def test_await_sleep_runs_concurrently(
    client: TestClient,
    make_auth,
    monkeypatch,
) -> None:
    """用 await 让出控制权：两个 0.5 秒的请求，总耗时约 0.5 秒。"""

    async def slow_stream(prompt: str, **kwargs):
        await asyncio.sleep(0.5)
        yield "ok"

    monkeypatch.setattr(chat, "astream", slow_stream)

    alice = make_auth()
    bob = make_auth()
    alice_conversation = _conversation(client, alice)
    bob_conversation = _conversation(client, bob)

    payloads = [
        {"conversation_id": alice_conversation, "message": "hi"},
        {"conversation_id": bob_conversation, "message": "hi"},
    ]
    statuses, elapsed = asyncio.run(_chat_pair(payloads, [alice, bob]))

    assert statuses == [200, 200]
    # 串行需要 1.0 秒以上；并发应该在 0.5 秒左右
    assert elapsed < 0.9


def test_blocking_sleep_serializes(
    client: TestClient,
    make_auth,
    monkeypatch,
) -> None:
    """在协程里调用 time.sleep：事件循环被堵住，两个请求变成串行。"""

    async def blocking_stream(prompt: str, **kwargs):
        time.sleep(0.5)
        yield "ok"

    monkeypatch.setattr(chat, "astream", blocking_stream)

    alice = make_auth()
    bob = make_auth()
    alice_conversation = _conversation(client, alice)
    bob_conversation = _conversation(client, bob)

    payloads = [
        {"conversation_id": alice_conversation, "message": "hi"},
        {"conversation_id": bob_conversation, "message": "hi"},
    ]
    statuses, elapsed = asyncio.run(_chat_pair(payloads, [alice, bob]))

    assert statuses == [200, 200]
    # 两个 0.5 秒只能排队，总耗时 1.0 秒以上
    assert elapsed > 0.95

