"""
Tests for password hashing and JWT issuance/verification. Security-critical
code that was previously only exercised indirectly through API tests —
tested directly here so a failure points straight at core/security.py
instead of surfacing as a confusing 401 somewhere in tests/api/.
"""
from jose import jwt

from src.core.config import get_settings
from src.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_round_trip():
    hashed = hash_password("supersecret123")

    assert hashed != "supersecret123"  # never store plaintext
    assert verify_password("supersecret123", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("supersecret123")

    assert verify_password("wrongpassword", hashed) is False


def test_create_and_decode_access_token_round_trip():
    token = create_access_token(subject="alice@example.com")

    assert decode_access_token(token) == "alice@example.com"


def test_decode_access_token_returns_none_for_garbage_token():
    assert decode_access_token("not.a.real.jwt.token") is None


def test_decode_access_token_returns_none_for_wrong_signature():
    # Signed with a different secret than the app uses — simulates a
    # forged/tampered token, the exact case decode_access_token must reject.
    settings = get_settings()
    forged = jwt.encode(
        {"sub": "attacker@example.com"}, "wrong-secret-key", algorithm=settings.jwt_algorithm
    )

    assert decode_access_token(forged) is None


def test_decode_access_token_returns_none_for_expired_token():
    settings = get_settings()
    from datetime import datetime, timedelta, timezone

    expired_payload = {
        "sub": "alice@example.com",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(
        expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )

    assert decode_access_token(expired_token) is None
