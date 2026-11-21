from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..models import User


def get_current_owner(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Phase 1 single-user owner resolver. In Phase 2 SaaS, swap this with JWT auth."""
    owner = db.execute(select(User).where(User.email == settings.default_owner_email)).scalar_one_or_none()
    if owner is None:
        owner = User(email=settings.default_owner_email, display_name="Studio Owner", plan_tier="personal")
        db.add(owner)
        db.commit()
        db.refresh(owner)
    return owner


def verify_worker_token(
    x_worker_token: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> None:
    if x_worker_token != settings.worker_shared_secret:
        raise HTTPException(status_code=401, detail="Invalid worker token")
