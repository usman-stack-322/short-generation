import base64
import hashlib
import hmac
import json
import secrets
import time
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.models import User, WorkspaceMember

bearer = HTTPBearer(auto_error=False)


def new_id() -> str:
    return str(uuid4())


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 310_000)
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_token(user_id: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": user_id, "exp": int(time.time()) + 86400}).encode()).decode().rstrip("=")
    signature = hmac.new(settings.app_secret_key.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def current_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    request: Request = None,
):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue")
    try:
        payload, signature = credentials.credentials.split(".", 1)
        expected = hmac.new(settings.app_secret_key.encode(), payload.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if not hmac.compare_digest(expected, supplied) or body["exp"] < int(time.time()):
            raise ValueError("Invalid or expired token")
    except (ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired session") from None
    user = db.get(User, body.get("sub"))
    req_ws = request.headers.get("x-workspace-id") if request else None
    membership = (
        db.query(WorkspaceMember).filter_by(user_id=user.id, workspace_id=req_ws, active=True).first()
        if (user and req_ws)
        else None
    )
    if not membership and user:
        membership = db.query(WorkspaceMember).filter_by(user_id=user.id, active=True).first()
    if not user or not membership:
        raise HTTPException(status_code=401, detail="Active workspace membership required")
    from datetime import datetime,timezone
    now=datetime.now(timezone.utc)
    last=membership.last_active_at
    if last is None or (now-last.replace(tzinfo=timezone.utc)).total_seconds()>300:
        membership.last_active_at=now
        db.commit()
    return user, membership


def require_owner(context=Depends(current_context)):
    user, membership = context
    if membership.role != "OWNER":
        raise HTTPException(status_code=403, detail="Owner access required")
    return user, membership


def require_editor(context=Depends(current_context)):
    if context[1].role not in {"OWNER", "ADMIN", "MEMBER", "EDITOR"}:
        raise HTTPException(status_code=403, detail="Editor or owner access required")
    return context


def require_admin(context=Depends(current_context)):
    if context[1].role not in {"OWNER", "ADMIN"}:
        raise HTTPException(403, "Administrator access required")
    return context
