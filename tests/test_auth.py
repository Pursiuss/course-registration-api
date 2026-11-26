"""Unit tests for auth.py: password hashing, JWTs and the user store."""
from datetime import datetime, timedelta, timezone

import jwt

import auth


def test_passwords_are_salted_hashes_not_plain_text():
    first = auth.hash_password("Secret-1")
    second = auth.hash_password("Secret-1")
    assert first != second  # a new random salt every time
    assert b"Secret-1" not in first
    assert auth.check_password("Secret-1", first)
    assert not auth.check_password("wrong", first)


def test_register_then_authenticate():
    assert auth.register_user("unit-alice", "pw-1")
    assert not auth.register_user("unit-alice", "other")  # duplicate
    assert auth.authenticate("unit-alice", "pw-1")["role"] == "student"
    assert auth.authenticate("unit-alice", "nope") is None
    assert auth.authenticate("unit-nobody", "pw-1") is None


def test_admin_is_seeded():
    assert auth.authenticate("admin", "admin")["role"] == "admin"


def test_token_carries_sub_and_role():
    claims = auth.decode_token(auth.create_token("unit-bob", "student"))
    assert claims["sub"] == "unit-bob"
    assert claims["role"] == "student"


def test_bad_tokens_are_rejected():
    assert auth.decode_token("not-a-jwt") is None

    # Signed with a different key: someone trying to make themselves admin.
    forged = jwt.encode({"sub": "admin", "role": "admin"},
                        "a-key-that-is-not-the-server-key-123", algorithm="HS256")
    assert auth.decode_token(forged) is None

    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    expired = jwt.encode({"sub": "unit-bob", "role": "student", "exp": past},
                         auth.SECRET_KEY, algorithm="HS256")
    assert auth.decode_token(expired) is None


def test_long_passwords_do_not_crash():
    long_password = "x" * 100  # bcrypt's limit is 72 bytes
    assert auth.check_password(long_password, auth.hash_password(long_password))
