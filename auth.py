"""
Phase 4 authentication: password hashing, JWTs and the in-memory user store.

Pure functions (no FastAPI), like audit.py, so they're easy to unit-test.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

# Key used to sign tokens. Set JWT_SECRET on Render to keep it stable;
# otherwise a random key is made at startup. Users live in memory and
# vanish on restart anyway, so old tokens dying with them is fine.
SECRET_KEY = os.environ.get("JWT_SECRET") or secrets.token_urlsafe(32)
ALGORITHM = "HS256"
TOKEN_MINUTES = 60

# username -> {"password_hash": bytes, "role": "student" | "admin"}
users: dict[str, dict] = {}


def _password_bytes(password: str) -> bytes:
    """bcrypt only reads the first 72 bytes, and bcrypt 5 raises an error
    on anything longer, so cut it to 72 the same way every time."""
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> bytes:
    """Salted bcrypt hash. gensalt() makes a new random salt every call."""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt())


def check_password(password: str, password_hash: bytes) -> bool:
    return bcrypt.checkpw(_password_bytes(password), password_hash)


def register_user(username: str, password: str, role: str = "student") -> bool:
    """Store a new user. Returns False if the username is already taken."""
    if username in users:
        return False
    users[username] = {"password_hash": hash_password(password), "role": role}
    return True


def authenticate(username: str, password: str) -> dict | None:
    """Return the user's record if the password matches, else None."""
    user = users.get(username)
    if user is None or not check_password(password, user["password_hash"]):
        return None
    return user


def create_token(username: str, role: str) -> str:
    """Signed JWT with the claims the spec asks for: sub and role."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Claims of a valid token, or None if it's forged, expired or garbage."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None


# The hardcoded admin account the spec requires (admin / admin).
register_user("admin", "admin", role="admin")
