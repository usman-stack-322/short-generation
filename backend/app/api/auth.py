from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_token, current_context, hash_password, new_id, verify_password
from app.database.session import get_db
from app.models import User, Workspace, WorkspaceMember
from app.schemas import ForgotPasswordInput, LoginInput, RegisterInput, ResetPasswordInput
from app.services.account_codes import can_issue, consume_code, delivery_mode, issue_code, send_code


router = APIRouter()
generated_dir = Path(settings.generated_dir).resolve()


def _is_https_request(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
    origin = (request.headers.get("origin") or "").lower()
    return proto.startswith("https") or origin.startswith("https://")


@router.post('/api/auth/media-session')
def media_session(request: Request, response: Response, context=Depends(current_context)):
    # This cookie is read ONLY by the read-only media route, never mutation APIs.
    https = _is_https_request(request)
    samesite = 'none' if https else 'lax'
    token = create_token(context[0].id)
    for cookie_path in ('/generated', '/api/library/media', '/api/title-shorts', '/api/assets/vault'):
        response.set_cookie(
            'media_session', token, httponly=True,
            samesite=samesite, secure=https, path=cookie_path, max_age=86400,
        )
    return {'configured': True}


@router.post('/api/auth/logout')
def logout(request: Request, response: Response):
    https = _is_https_request(request)
    samesite = 'none' if https else 'lax'
    for cookie_path in ('/generated', '/api/library/media', '/api/title-shorts', '/api/assets/vault'):
        response.delete_cookie('media_session', path=cookie_path, samesite=samesite, secure=https)
    return {'signed_out': True}


def _auth_response(user: User, membership: WorkspaceMember) -> dict:
    return {
        "access_token": create_token(user.id),
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "role": membership.role,
        "workspace_id": membership.workspace_id,
    }


@router.post("/api/auth/register", status_code=201)
def register(payload: RegisterInput, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists. Please sign in.")
    display = payload.name.strip() or "Studio Creator"
    workspace = Workspace(id=new_id(), name=f"{display}'s Studio")
    user = User(id=new_id(), name=display, email=email, password_hash=hash_password(payload.password))
    db.add_all([workspace, user])
    db.flush()
    membership = WorkspaceMember(id=new_id(), workspace_id=workspace.id, user_id=user.id, role="OWNER", active=True)
    db.add(membership)
    db.commit()
    return _auth_response(user, membership)


@router.post("/api/auth/login")
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    membership = db.query(WorkspaceMember).filter_by(user_id=user.id, active=True).first()
    if not membership:
        raise HTTPException(status_code=403, detail="This account has no active workspace membership.")
    return _auth_response(user, membership)


@router.post("/api/auth/forgot-password")
def forgot_password(payload: ForgotPasswordInput, db: Session = Depends(get_db)):
    email = payload.email.lower()
    user = db.query(User).filter_by(email=email).first()
    mode = delivery_mode()
    if user:
        membership = db.query(WorkspaceMember).filter_by(user_id=user.id, active=True).first()
        if membership and can_issue(db, user):
            code = issue_code(db, user, purpose="reset")
            mode = send_code(user.email, user.name, code, purpose="reset")
    return {
        "sent": True,
        "delivery_mode": mode,
        "message": (
            "If an active account matches that email, a 6-digit verification code has been sent."
            if mode == "smtp"
            else "If an active account matches that email, a 6-digit verification code was issued (check the backend terminal log in local dev mode when SMTP is not configured)."
        ),
    }


@router.post("/api/auth/reset-password")
def reset_password(payload: ResetPasswordInput, db: Session = Depends(get_db)):
    email = payload.email.lower()
    user = db.query(User).filter_by(email=email).first()
    if not user or not consume_code(db, user, payload.code):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code. Request a new code and try again.")
    membership = db.query(WorkspaceMember).filter_by(user_id=user.id, active=True).first()
    if not membership:
        raise HTTPException(status_code=403, detail="This account has no active workspace membership.")
    user.password_hash = hash_password(payload.new_password)
    if not user.email_verified_at:
        user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "reset": True,
        "access_token": create_token(user.id),
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "role": membership.role,
        "workspace_id": membership.workspace_id,
    }


@router.get("/api/auth/me")
def me(context=Depends(current_context)):
    user, membership = context
    ws_name = membership.workspace.name if membership.workspace else membership.workspace_id
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": membership.role,
        "workspace_id": membership.workspace_id,
        "workspace_name": ws_name,
        "can_manage_admins": membership.can_manage_admins,
    }
