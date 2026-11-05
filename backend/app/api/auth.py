from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status,Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_token, current_context, hash_password, new_id, verify_password
from app.database.session import get_db
from app.models import User, Workspace, WorkspaceMember
from app.schemas import LoginInput, RegisterInput


router = APIRouter()
generated_dir = Path(settings.generated_dir).resolve()


@router.post('/api/auth/media-session')
def media_session(response:Response,context=Depends(current_context)):
    # This cookie is read ONLY by the read-only media route, never mutation APIs.
    response.set_cookie('media_session',create_token(context[0].id),httponly=True,samesite='lax',path='/generated',max_age=86400)
    response.set_cookie('media_session',create_token(context[0].id),httponly=True,samesite='lax',path='/api/library/media',max_age=86400)
    response.set_cookie('media_session',create_token(context[0].id),httponly=True,samesite='lax',path='/api/title-shorts',max_age=86400)
    return {'configured':True}


@router.post('/api/auth/logout')
def logout(response:Response):
    response.delete_cookie('media_session',path='/generated')
    response.delete_cookie('media_session',path='/api/library/media')
    response.delete_cookie('media_session',path='/api/title-shorts')
    return {'signed_out':True}

@router.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterInput, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(id=new_id(), name=payload.name.strip(), email=email, password_hash=hash_password(payload.password))
    workspace = Workspace(id=new_id(), name=payload.workspace_name.strip())
    db.add_all([user, workspace])
    db.flush()
    membership = WorkspaceMember(id=new_id(), workspace_id=workspace.id, user_id=user.id, role="MEMBER")
    db.add(membership)
    db.commit()
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": {"id": user.id, "name": user.name, "email": user.email}, "role": membership.role}


@router.post("/api/auth/login")
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    membership = db.query(WorkspaceMember).filter_by(user_id=user.id, active=True).first()
    if not membership:
        raise HTTPException(status_code=403, detail="This account has no active workspace membership.")
    return {
        "access_token": create_token(user.id), "token_type": "bearer",
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "role": membership.role, "workspace_id": membership.workspace_id,
    }


@router.get("/api/auth/me")
def me(context=Depends(current_context)):
    user, membership = context
    return {"id": user.id, "name": user.name, "email": user.email, "role": membership.role, "workspace_id": membership.workspace_id,"can_manage_admins":membership.can_manage_admins}


