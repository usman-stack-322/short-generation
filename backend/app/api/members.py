"""Platform account administration. Audit fields are explicitly allowlisted."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.security import hash_password, new_id, require_admin
from app.database.session import get_db
from app.models import User, Workspace, WorkspaceMember, AdminAudit, VideoJob
from app.schemas import MemberInput, MemberStatusInput

router = APIRouter()


def audit(db, actor, target, action, details):
    db.add(AdminAudit(id=new_id(),workspace_id=actor.workspace_id,actor_id=actor.id,
        target_id=target.id,action=action,details=json.dumps(details)))


def public(m):
    return dict(id=m.id,user_id=m.user_id,name=m.user.name,email=m.user.email,role=m.role,
        active=m.active,can_manage_admins=m.can_manage_admins,created_at=m.created_at.isoformat())


@router.get('/api/members')
def listing(context=Depends(require_admin),db:Session=Depends(get_db)):
    return [public(m) for m in db.query(WorkspaceMember).all()]


@router.get('/api/members/audit')
def history(context=Depends(require_admin),db:Session=Depends(get_db)):
    return [dict(id=r.id,actor_id=r.actor_id,target_id=r.target_id,action=r.action,
        details=json.loads(r.details),created_at=r.created_at.isoformat())
        for r in db.query(AdminAudit).order_by(AdminAudit.created_at.desc()).limit(200)]


@router.get('/api/members/operations')
def operations(context=Depends(require_admin),db:Session=Depends(get_db)):
    return [dict(id=j.id,status=j.status,current_step=j.current_step,retry_count=j.retry_count,
        created_at=j.created_at.isoformat()) for j in db.query(VideoJob).order_by(VideoJob.created_at.desc()).limit(100)]


@router.post('/api/members',status_code=201)
def create_member(payload:MemberInput,context=Depends(require_admin),db:Session=Depends(get_db)):
    actor=context[1]
    if payload.role=='ADMIN' and actor.role!='OWNER' and not actor.can_manage_admins:
        raise HTTPException(403,'Only an Owner or explicitly delegated Admin may appoint Admins')
    if db.query(User).filter_by(email=payload.email.lower()).first():
        raise HTTPException(409,'This email is already registered')
    password='Temp-'+new_id()+'-9a!'
    user=User(id=new_id(),name=payload.name,email=payload.email.lower(),password_hash=hash_password(password))
    workspace=Workspace(id=new_id(),name=payload.name+' workspace')
    db.add_all([user,workspace]);db.flush()
    member=WorkspaceMember(id=new_id(),workspace_id=workspace.id,user_id=user.id,role=payload.role)
    db.add(member);db.flush();audit(db,actor,member,'member_created',{'role':member.role})
    db.commit()
    return {**public(member),'temporary_password':password}


@router.patch('/api/members/{member_id}')
def change(member_id:str,payload:MemberStatusInput,context=Depends(require_admin),db:Session=Depends(get_db)):
    if db.bind.dialect.name=='sqlite':
        db.execute(text('UPDATE workspace_members SET active=active WHERE id=:id'),{'id':context[1].id})
    else:
        db.query(WorkspaceMember).filter_by(role='OWNER').with_for_update().all()
    target=db.get(WorkspaceMember,member_id);actor=context[1]
    db.refresh(actor)
    if actor.role not in {'OWNER','ADMIN'} or not actor.active:raise HTTPException(403,'Administrator access required')
    if not target:raise HTTPException(404,'Member not found')
    changes=payload.model_dump(exclude_none=True)
    if not changes:raise HTTPException(422,'Supply a role, active status or delegation')
    if actor.role!='OWNER':
        if target.role=='OWNER' or changes.get('role')=='OWNER' or 'can_manage_admins' in changes:
            raise HTTPException(403,'Only an Owner may manage Owners or administrator delegation')
        if ('role' in changes or target.role=='ADMIN') and not actor.can_manage_admins:
            raise HTTPException(403,'Owner delegation required to manage administrators')
    if target.id==actor.id and changes.get('active') is False:
        raise HTTPException(409,'You cannot deactivate your own account')
    if target.role=='OWNER' and target.active and (changes.get('active') is False or changes.get('role','OWNER')!='OWNER'):
        if db.query(WorkspaceMember).filter_by(role='OWNER',active=True).count()<=1:
            raise HTTPException(409,'The platform must retain an active Owner')
    before={k:getattr(target,k) for k in changes}
    for key,value in changes.items():setattr(target,key,value)
    if target.role!='ADMIN':target.can_manage_admins=False
    audit(db,actor,target,'member_updated',{'before':before,'after':changes})
    db.commit();return public(target)
