"""认证接口的集成测试。

需要 PostgreSQL 在跑：conftest 里的 db_available fixture 会统一处理 skip。
"""

import uuid

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str, password: str = "password123") -> dict:
    resp = client.post("/v1/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _login(client: TestClient, email: str, password: str = "password123") -> dict:
    resp = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_register_returns_only_public_fields(client: TestClient, email: str) -> None:
    body = _register(client, email)
    assert body["email"] == email
    assert body["id"]
    assert body["created_at"]
    # 响应里绝不能出现密码哈希
    assert "password_hash" not in body


def test_duplicate_email_returns_409(client: TestClient, email: str) -> None:
    _register(client, email)
    resp = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "CONFLICT"
    assert resp.json()["message"] == "邮箱已被注册"


def test_email_is_normalized_to_lowercase(client: TestClient, email: str) -> None:
    body = _register(client, email.upper())
    assert body["email"] == email.lower()
    # 注册时大写、登录时小写，仍然匹配同一个账号
    assert _login(client, email.lower())["token_type"] == "bearer"


def test_wrong_password_and_unknown_user_look_the_same(client: TestClient, email: str) -> None:
    _register(client, email)
    wrong = client.post(
        "/v1/auth/login",
        json={"email": email, "password": "wrong-password"},
    )
    unknown = client.post(
        "/v1/auth/login",
        json={"email": f"nobody-{uuid.uuid4().hex}@example.com", "password": "password123"},
    )
    # 两种情况的状态码和提示必须一致，否则等于帮攻击者枚举邮箱
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["message"] == unknown.json()["message"]


def test_me_requires_valid_access_token(client: TestClient, email: str) -> None:
    _register(client, email)
    tokens = _login(client, email)

    ok = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert ok.status_code == 200
    assert ok.json()["email"] == email

    missing = client.get("/v1/auth/me")
    assert missing.status_code == 401
    assert missing.json()["code"] == "UNAUTHORIZED"


def test_refresh_token_issues_new_pair(client: TestClient, email: str) -> None:
    _register(client, email)
    tokens = _login(client, email)

    resp = client.post(
        "/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    # 新 access 能正常调业务接口
    ok = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert ok.status_code == 200


def test_refresh_token_cannot_call_business_api(client: TestClient, email: str) -> None:
    _register(client, email)
    tokens = _login(client, email)

    resp = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert resp.status_code == 401


def test_access_token_cannot_be_refreshed(client: TestClient, email: str) -> None:
    _register(client, email)
    tokens = _login(client, email)

    resp = client.post(
        "/v1/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert resp.status_code == 401


def test_short_password_is_rejected(client: TestClient, email: str) -> None:
    resp = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "short"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["detail"][0]["loc"] == ["body", "password"]


def test_garbage_refresh_token_returns_401(client: TestClient, email: str) -> None:
    _register(client, email)
    resp = client.post("/v1/auth/refresh", json={"refresh_token": "not-a-token"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"
