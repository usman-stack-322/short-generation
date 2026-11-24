from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..models import User, utcnow
from ..schemas import AuthLoginRequest, AuthRegisterRequest, AuthResponse, UserOut
from ..services.auth_security import create_access_token, hash_password, verify_password
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name or "Studio Owner",
        plan_tier=user.plan_tier or "personal",
        created_at=user.created_at,
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register_user(
    payload: AuthRegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Create a new user account (or claim an unauthenticated legacy owner row) and return a JWT."""
    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        if existing.hashed_password:
            raise HTTPException(status_code=409, detail="An account with this email already exists.")
        existing.hashed_password = password_hash
        if payload.display_name and payload.display_name.strip():
            existing.display_name = payload.display_name.strip()
        if not existing.display_name:
            existing.display_name = payload.email.split("@", 1)[0][:120] or "Creator"
        if not existing.plan_tier:
            existing.plan_tier = "personal"
        if existing.created_at is None:
            existing.created_at = utcnow()
        user = existing
    else:
        default_name = payload.email.split("@", 1)[0][:120] or "Creator"
        display_name = (payload.display_name or "").strip() or default_name
        user = User(
            email=payload.email,
            hashed_password=password_hash,
            display_name=display_name,
            plan_tier="personal",
        )
        db.add(user)

    db.commit()
    db.refresh(user)
    token = create_access_token(user_id=user.id, email=user.email, settings=settings)
    return AuthResponse(access_token=token, user=_to_user_out(user))


@router.post("/login", response_model=AuthResponse)
def login_user(
    payload: AuthLoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Verify credentials against bcrypt hash and return a signed JWT access token."""
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(user_id=user.id, email=user.email, settings=settings)
    return AuthResponse(access_token=token, user=_to_user_out(user))


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user profile."""
    return _to_user_out(current_user)
