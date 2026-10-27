"""API 探针与聊天接口测试。"""

from fastapi.testclient import TestClient

from apps.api import main

client = TestClient(main.app)


def test_healthz() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_ok(monkeypatch) -> None:
    async def fake_ok(host: str, port: int) -> bool:
        return True

    monkeypatch.setattr(main, "_tcp_ok", fake_ok)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


def test_readyz_degraded(monkeypatch) -> None:
    async def fake_fail(host: str, port: int) -> bool:
        return False

    monkeypatch.setattr(main, "_tcp_ok", fake_fail)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["ready"] is False


def test_chat_rejects_empty(monkeypatch) -> None:
    resp = client.post("/v1/chat", json={"message": ""})
    assert resp.status_code == 422


def test_chat_stream(monkeypatch) -> None:
    async def fake_stream(prompt: str, system: str | None = None, temperature: float = 0.2):
        for piece in ["你", "好"]:
            yield piece

    monkeypatch.setattr(main, "astream", fake_stream)
    with client.stream("POST", "/v1/chat", json={"message": "hi"}) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert '"delta": "你"' in body
    assert '"delta": "好"' in body
    assert "data: [DONE]" in body
