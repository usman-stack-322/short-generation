from typing import Optional

from fastapi import Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..models import User
from ..services.auth_security import decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


def _resolve_user_from_token(raw_token: str, db: Session, settings: Settings) -> User:
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(raw_token, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = db.execute(select(User).where(User.id == payload["sub"])).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User account not found")
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Resolve authenticated studio user from Authorization: Bearer <jwt> header."""
    if not credentials or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _resolve_user_from_token(credentials.credentials, db=db, settings=settings)


def get_current_user_from_header_or_query(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    token: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Resolve user from Bearer header or ?token=<jwt> query param (for browser video tags)."""
    raw_token = (
        credentials.credentials
        if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials
        else (token or "").strip()
    )
    return _resolve_user_from_token(raw_token, db=db, settings=settings)


def get_current_owner(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Default owner fallback for trusted internal worker calls that do not specify x-owner-id."""
    owner = db.execute(select(User).where(User.email == settings.default_owner_email)).scalar_one_or_none()
    if owner is None:
        owner = User(email=settings.default_owner_email, display_name="Studio Owner", plan_tier="personal")
        db.add(owner)
        db.commit()
        db.refresh(owner)
    return owner


def get_current_user_or_worker(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    x_worker_token: str = Header(default=""),
    x_owner_id: str = Header(default=""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Authenticate either via User Bearer JWT or via Local PC Worker x-worker-token."""
    if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials:
        return _resolve_user_from_token(credentials.credentials, db=db, settings=settings)

    if x_worker_token and x_worker_token == settings.worker_shared_secret:
        if x_owner_id:
            target = db.execute(select(User).where(User.id == x_owner_id)).scalar_one_or_none()
            if target is not None:
                return target
        return get_current_owner(db=db, settings=settings)

    raise HTTPException(status_code=401, detail="Authentication required")


def verify_worker_token(
    x_worker_token: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> None:
    if x_worker_token != settings.worker_shared_secret:
        raise HTTPException(status_code=401, detail="Invalid worker token")
