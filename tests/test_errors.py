"""统一错误响应与 trace_id 的测试。"""

from fastapi.testclient import TestClient

from apps.api.errors import ConflictError, NotFoundError
from apps.api.main import create_app

app = create_app()


@app.get("/_test/not-found")
async def _raise_not_found() -> None:
    raise NotFoundError("会话不存在")


@app.get("/_test/conflict")
async def _raise_conflict() -> None:
    raise ConflictError("邮箱已被注册", detail={"field": "email"})


@app.get("/_test/boom")
async def _raise_boom() -> None:
    raise RuntimeError("postgres password=secret")


# 500 的兜底处理器会先发响应、再把异常重新抛出。
# 关掉 raise_server_exceptions，测试里才能拿到那个 500 响应。
client = TestClient(app, raise_server_exceptions=False)


def test_framework_404_uses_unified_shape() -> None:
    resp = client.get("/_test/no-such-route")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "HTTP_404"
    assert body["message"] == "Not Found"
    assert body["detail"] is None
    assert body["trace_id"]
    assert resp.headers["X-Trace-Id"] == body["trace_id"]


def test_validation_error_uses_unified_shape() -> None:
    # 用公开的登录接口：缺字段在进 handler 之前就被拦下，不需要登录和数据库
    resp = client.post("/v1/auth/login", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "请求参数校验失败"
    assert body["detail"][0]["loc"] == ["body", "email"]
    assert body["trace_id"]


def test_app_error_maps_to_http_status() -> None:
    resp = client.get("/_test/not-found")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["message"] == "会话不存在"
    assert body["detail"] is None


def test_app_error_keeps_detail() -> None:
    resp = client.get("/_test/conflict")
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "CONFLICT"
    assert body["detail"] == {"field": "email"}


def test_unhandled_error_hides_internals() -> None:
    resp = client.get("/_test/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["message"] == "服务器内部错误"
    assert body["detail"] is None
    assert "secret" not in body["message"]


def test_405_uses_unified_shape() -> None:
    resp = client.post("/healthz")
    assert resp.status_code == 405
    assert resp.json()["code"] == "HTTP_405"


def test_trace_id_from_request_header_is_reused() -> None:
    resp = client.get("/_test/no-such-route", headers={"X-Trace-Id": "trace-abc"})
    assert resp.headers["X-Trace-Id"] == "trace-abc"
    assert resp.json()["trace_id"] == "trace-abc"
