"""Password hashing (bcrypt) and JWT token helpers for studio authentication."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from jwt import PyJWTError

from ..config import Settings, get_settings


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt after checking the 72-byte bcrypt limit."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("Password must be 72 UTF-8 bytes or fewer.")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed_password: Optional[str]) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    if not password or not hashed_password:
        return False
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        return False
    try:
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    user_id: str,
    email: str,
    settings: Optional[Settings] = None,
) -> str:
    """Create a signed HS256 JWT access token for a studio user."""
    active = settings or get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(hours=max(1, int(active.jwt_expire_hours))),
    }
    return jwt.encode(payload, active.jwt_secret, algorithm=active.jwt_algorithm)


def decode_access_token(token: str, settings: Optional[Settings] = None) -> dict:
    """Decode and verify an HS256 JWT access token."""
    active = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            active.jwt_secret,
            algorithms=[active.jwt_algorithm],
        )
    except PyJWTError as exc:
        raise ValueError("Invalid or expired authentication token") from exc
    if not payload.get("sub"):
        raise ValueError("Authentication token is missing subject")
    return payload
