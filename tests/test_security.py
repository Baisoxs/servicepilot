"""密码哈希与 JWT 的测试。"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from packages.core.config import get_settings
from packages.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_is_hashed_and_verifiable() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_same_password_gets_different_hashes() -> None:
    first = hash_password("same-password")
    second = hash_password("same-password")
    # 每次哈希都用新的随机盐，所以两个结果不一样
    assert first != second
    assert verify_password("same-password", first)
    assert verify_password("same-password", second)


def test_access_token_roundtrip() -> None:
    token = create_access_token("user-1")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"


def test_refresh_token_cannot_be_used_as_access_token() -> None:
    token = create_refresh_token("user-1")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, expected_type="access")


def test_expired_token_is_rejected() -> None:
    settings = get_settings()
    payload = {
        "sub": "user-1",
        "type": "access",
        "exp": datetime.now(UTC) - timedelta(seconds=1),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, expected_type="access")


def test_tampered_token_is_rejected() -> None:
    token = create_access_token("user-1")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{'x' * len(signature)}"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tampered, expected_type="access")
