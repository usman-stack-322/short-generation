"""Studio APIs: Celebrity Vault, Scene Manual Upload, Review Queue, YouTube Upload, Workspaces & Team RBAC."""
import hashlib
import json
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.title_shorts import access, claim, delete_accessible_draft, media_context, public
from app.core.config import settings
from app.core.security import create_token, current_context, hash_password, new_id, require_admin, require_editor
from app.database.session import get_db
from app.models import (
    AdminAudit,
    Channel,
    ChannelAuthorization,
    CelebrityAsset,
    CelebrityFolder,
    TitleShortDraft,
    User,
    Workspace,
    WorkspaceInvite,
    WorkspaceMember,
)
from app.schemas import InviteAcceptInput, InviteLinkCreateInput
from app.services.celebrity_vault import (
    ALLOWED_EXTS,
    GENERIC_SUBFOLDERS,
    VIDEO_EXTS,
    list_celebrity_library,
    scan_celebrity_folder,
    stage_vault_asset_for_draft,
)
from app.services.title_shorts import directory

router = APIRouter(tags=['Studio'])


class ConnectFolderInput(BaseModel):
    folder_path: str = Field(min_length=1, max_length=1000)
    preference: str = Field(default='mix_both')


class WorkspaceInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)


class TeamInviteInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role: str = Field(default='MEMBER')


class RoleUpdateInput(BaseModel):
    role: str = Field(min_length=3, max_length=20)


class ReviewActionInput(BaseModel):
    action: str = Field(pattern='^(approve|reject|request_changes)$')
    note: str = Field(default='', max_length=1000)


class YouTubeUploadInput(BaseModel):
    channel_id: str | None = None
    title: str = Field(default='', max_length=100)
    description: str = Field(default='', max_length=4000)
    privacy_status: str = Field(default='private', pattern='^(private|unlisted|public)$')


@router.post('/api/assets/connect-folder')
def connect_folder(payload: ConnectFolderInput, context=Depends(require_admin), db: Session = Depends(get_db)):
    if payload.preference not in {'mix_both', 'prefer_clips', 'prefer_images'}:
        raise HTTPException(422, 'Preference must be mix_both, prefer_clips, or prefer_images')
    try:
        return scan_celebrity_folder(db, context[1].workspace_id, payload.folder_path, payload.preference)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get('/api/assets/library')
def assets_library(limit: int = 12, context=Depends(current_context), db: Session = Depends(get_db)):
    return list_celebrity_library(db, context[1].workspace_id, limit_per_celebrity=limit)


def _safe_rel_subdir(orig: Path, override_celebrity: str) -> Path:
    if override_celebrity.strip():
        safe = ''.join(ch for ch in override_celebrity.strip() if ch not in '\\/:*?"<>|')
        return Path(safe) if safe else Path('.')
    parts = [p for p in orig.parts[:-1] if p not in {'', '.', '..'}]
    if len(parts) >= 2:
        # Strip the top-level wrapper folder name when uploading a main parent folder (e.g. MainVault/Celebrity/file)
        sub_parts = parts[1:]
        # If stripping leaves only generic folders or empty, keep original parent
        if any(p.lower() not in GENERIC_SUBFOLDERS for p in sub_parts):
            return Path(*sub_parts)
    if parts:
        return Path(*parts)
    return Path('.')


@router.post('/api/assets/upload-bulk')
def upload_bulk(
    celebrity_name: str = Form(''),
    skip_scan: bool = Form(False),
    files: list[UploadFile] = File(...),
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    workspace_id = context[1].workspace_id
    folder_row = db.get(CelebrityFolder, workspace_id)
    if folder_row and Path(folder_row.folder_path).is_dir():
        root = Path(folder_row.folder_path)
    else:
        root = Path(settings.generated_dir).resolve() / 'celebrity_vault' / workspace_id
        root.mkdir(parents=True, exist_ok=True)
    saved = 0
    for f in files:
        orig = Path((f.filename or 'asset').replace('\\', '/'))
        ext = orig.suffix.lower()
        if ext not in ALLOWED_EXTS:
            continue
        rel_sub = _safe_rel_subdir(orig, celebrity_name)
        target_dir = root / rel_sub
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / orig.name
        with out_path.open('wb') as dst:
            shutil.copyfileobj(f.file, dst)
        if out_path.stat().st_size == 0:
            out_path.unlink(missing_ok=True)
            continue
        saved += 1
    if saved == 0 and not skip_scan:
        raise HTTPException(422, 'No supported image (.jpg/.png/.webp) or video (.mp4/.mov/.webm) files uploaded.')
    if skip_scan:
        return {'saved': saved, 'scanning': False, 'folder_path': str(root)}
    return scan_celebrity_folder(db, workspace_id, str(root), folder_row.preference if folder_row else 'mix_both')


@router.get('/api/assets/vault/{asset_id}/file')
def get_vault_file(asset_id: str, context=Depends(media_context), db: Session = Depends(get_db)):
    row = db.get(CelebrityAsset, asset_id)
    if not row or row.workspace_id != context[1].workspace_id:
        raise HTTPException(404, 'Celebrity asset not found')
    path = Path(row.file_path)
    if not path.is_file():
        raise HTTPException(404, 'Asset file missing on disk')
    return FileResponse(path, headers={'Cache-Control': 'private, no-store'}, content_disposition_type='inline')


@router.post('/api/projects/{project_id}/scenes/{scene_index}/upload-media')
async def upload_scene_media(
    project_id: str,
    scene_index: int,
    vault_asset_id: str = Form(''),
    file: UploadFile | None = File(None),
    context=Depends(require_editor),
    db: Session = Depends(get_db),
):
    row = access(db, project_id, context[1])
    data = json.loads(row.data)
    plan = data.get('plan')
    if not plan or not 1 <= scene_index <= len(plan.get('scenes', [])):
        raise HTTPException(404, 'Scene not found')
    locks = set(data.get('scene_locks', []))
    if scene_index in locks:
        raise HTTPException(409, 'Unlock scene before replacing media')
    assets = data.get('assets') or [None] * len(plan['scenes'])
    if len(assets) < len(plan['scenes']):
        assets.extend([None] * (len(plan['scenes']) - len(assets)))
    folder = directory(row) / 'assets'
    folder.mkdir(parents=True, exist_ok=True)

    if vault_asset_id.strip():
        vault_row = db.get(CelebrityAsset, vault_asset_id.strip())
        if not vault_row or vault_row.workspace_id != context[1].workspace_id:
            raise HTTPException(404, 'Celebrity vault asset not found')
        new_asset = stage_vault_asset_for_draft(vault_row, scene_index, folder)
    elif file is not None:
        ext = Path(file.filename or '').suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise HTTPException(422, 'Upload a supported image (.jpg/.png/.webp) or short video clip (.mp4/.mov/.webm).')
        body = await file.read()
        if not body or len(body) > 100 * 1024 * 1024:
            raise HTTPException(422, 'Uploaded file is empty or exceeds 100 MB.')
        out_path = folder / f'manual_s{scene_index}_{uuid4().hex[:10]}{ext}'
        out_path.write_bytes(body)
        media_type = 'video' if ext in VIDEO_EXTS else 'image'
        new_asset = {
            'path': str(out_path),
            'hash': hashlib.sha256(body).hexdigest(),
            'source_url': '',
            'creator': context[0].name,
            'license': 'Manual Scene Upload',
            'license_url': '',
            'credit': f'Uploaded for Scene {scene_index}: {file.filename}',
            'kind': 'manual_clip' if media_type == 'video' else 'manual_photo',
            'media_type': media_type,
            'provider': 'manual_upload',
            'note': f'Manually uploaded {media_type} ({file.filename}).',
        }
    else:
        raise HTTPException(422, 'Provide either a file upload or vault_asset_id.')

    claim(db, row, row.revision, 'script_review' if row.status in {'ready', 'script_review'} else row.status)
    assets[scene_index - 1] = new_asset
    data['assets'] = assets
    data.pop('video', None)
    data['review_status'] = 'draft'
    row.data = json.dumps(data, ensure_ascii=False)
    db.commit()
    return public(row)


@router.post('/api/projects/{project_id}/submit-review')
def submit_project_review(
    project_id: str,
    context=Depends(require_editor),
    db: Session = Depends(get_db),
):
    row = access(db, project_id, context[1])
    data = json.loads(row.data)
    if not data.get('video'):
        raise HTTPException(409, 'Render the short before submitting for approval.')
    if data.get('review_status') not in {'approved', 'uploaded'}:
        data['review_status'] = 'pending_review'
        data['submitted_for_review_at'] = datetime.now(timezone.utc).isoformat()
        row.data = json.dumps(data, ensure_ascii=False)
        db.commit()
    return public(row)


@router.delete('/api/projects/{project_id}')
def delete_project(
    project_id: str,
    context=Depends(require_editor),
    db: Session = Depends(get_db),
):
    return delete_accessible_draft(db, project_id, context[1])


@router.post('/api/projects/{project_id}/review')
def review_project(
    project_id: str,
    payload: ReviewActionInput,
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = access(db, project_id, context[1])
    data = json.loads(row.data)
    if payload.action == 'approve':
        if not data.get('video'):
            raise HTTPException(409, 'Render the short before approving.')
        data['review_status'] = 'approved'
    elif payload.action == 'reject':
        data['review_status'] = 'rejected'
    else:
        data['review_status'] = 'draft'
    data['review_note'] = payload.note
    data['reviewed_by'] = context[0].name
    data['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    row.data = json.dumps(data, ensure_ascii=False)
    db.commit()
    return public(row)


@router.post('/api/projects/{project_id}/upload-youtube')
def upload_project_youtube(
    project_id: str,
    payload: YouTubeUploadInput,
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = access(db, project_id, context[1])
    data = json.loads(row.data)
    video_info = data.get('video')
    if not video_info or not Path(video_info.get('path', '')).is_file():
        raise HTTPException(409, 'Rendered MP4 video not found. Render the short first.')
    if data.get('review_status') not in {'approved', 'pending_review', 'uploaded'}:
        raise HTTPException(409, 'Short must be rendered before uploading to YouTube.')

    title = (payload.title or (data.get('scope') or {}).get('proposed_title') or row.title).strip()[:100]
    if '#Shorts' not in title and len(title) <= 92:
        title = f'{title} #Shorts'
    description = (payload.description or (data.get('analysis') or {}).get('angle') or row.title).strip()[:4000]
    if '#Shorts' not in description:
        description = f'{description}\n\n#Shorts'

    channel_id = payload.channel_id or data.get('channel_id')
    auth_row = db.query(ChannelAuthorization).filter_by(channel_id=channel_id).first() if channel_id else None
    client_secrets = Path(settings.generated_dir).resolve().parent / 'client_secrets.json'

    mode = 'mock_fallback'
    yt_id = f'mock_yt_{row.id[:8]}'
    yt_url = f'https://youtube.com/shorts/{yt_id}'

    if auth_row and auth_row.encrypted_tokens and client_secrets.is_file():
        try:
            from app.core.vault import decrypt_secret
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            tokens = json.loads(decrypt_secret(auth_row.encrypted_tokens))
            creds = Credentials(
                token=tokens.get('access_token'),
                refresh_token=tokens.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.youtube_client_id,
                client_secret=settings.youtube_client_secret,
            )
            service = build('youtube', 'v3', credentials=creds)
            media = MediaFileUpload(video_info['path'], chunksize=5 * 1024 * 1024, resumable=True, mimetype='video/mp4')
            req = service.videos().insert(
                part='snippet,status',
                body={
                    'snippet': {'title': title, 'description': description, 'tags': ['Shorts'], 'categoryId': '22'},
                    'status': {'privacyStatus': payload.privacy_status, 'selfDeclaredMadeForKids': False},
                },
                media_body=media,
            )
            resp = req.execute()
            yt_id = resp['id']
            yt_url = f'https://youtube.com/shorts/{yt_id}'
            mode = 'youtube_api'
        except Exception as exc:
            raise HTTPException(502, f'YouTube upload failed: {exc}') from None

    data['review_status'] = 'uploaded'
    data['youtube_video_id'] = yt_id
    data['youtube_url'] = yt_url
    data['youtube_privacy'] = payload.privacy_status
    data['uploaded_at'] = datetime.now(timezone.utc).isoformat()
    row.data = json.dumps(data, ensure_ascii=False)
    db.commit()
    return {
        'uploaded': True,
        'mode': mode,
        'youtube_video_id': yt_id,
        'youtube_url': yt_url,
        'privacy_status': payload.privacy_status,
        'draft': public(row),
    }


@router.get('/api/workspaces')
def list_workspaces(context=Depends(current_context), db: Session = Depends(get_db)):
    rows = db.query(WorkspaceMember).filter_by(user_id=context[0].id, active=True).all()
    return [
        {
            'workspace_id': m.workspace_id,
            'name': m.workspace.name if m.workspace else m.workspace_id,
            'role': m.role,
            'current': m.workspace_id == context[1].workspace_id,
        }
        for m in rows
    ]


@router.post('/api/workspaces', status_code=201)
def create_workspace(payload: WorkspaceInput, context=Depends(require_admin), db: Session = Depends(get_db)):
    ws = Workspace(id=new_id(), name=payload.name.strip())
    db.add(ws)
    db.flush()
    m = WorkspaceMember(id=new_id(), workspace_id=ws.id, user_id=context[0].id, role=context[1].role, active=True)
    db.add(m)
    db.commit()
    return {'workspace_id': ws.id, 'name': ws.name, 'role': m.role}


@router.post('/api/team/invite', status_code=201)
def invite_team_member(payload: TeamInviteInput, context=Depends(require_admin), db: Session = Depends(get_db)):
    actor = context[1]
    role = payload.role.upper()
    if role not in {'ADMIN', 'MEMBER'}:
        raise HTTPException(422, 'Role must be ADMIN or MEMBER')
    if role == 'ADMIN' and actor.role != 'OWNER':
        raise HTTPException(403, 'Only Owner may create a separate Partner/Admin workspace account')
    email = payload.email.lower()
    user = db.query(User).filter_by(email=email).first()
    if user:
        same_ws = db.query(WorkspaceMember).filter_by(workspace_id=actor.workspace_id, user_id=user.id).first()
        other_ws = db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.workspace_id != actor.workspace_id,
        ).first()
        if role == 'ADMIN' or other_ws or not same_ws:
            raise HTTPException(409, 'This email is already registered')

    temp_pw = None
    if not user:
        temp_pw = f'Temp-{new_id()[:8]}-9a!'
        user = User(id=new_id(), name=payload.name.strip(), email=email, password_hash=hash_password(temp_pw))
        db.add(user)
        db.flush()

    if role == 'ADMIN':
        ws = Workspace(id=new_id(), name=f'{payload.name.strip()} Workspace')
        db.add(ws)
        db.flush()
        target_ws = ws.id
        ws_name = ws.name
        isolated = True
    else:
        target_ws = actor.workspace_id
        ws_obj = db.get(Workspace, target_ws)
        ws_name = ws_obj.name if ws_obj else target_ws
        isolated = False

    existing = db.query(WorkspaceMember).filter_by(workspace_id=target_ws, user_id=user.id).first()
    if existing:
        existing.role = role
        existing.active = True
        member = existing
    else:
        member = WorkspaceMember(id=new_id(), workspace_id=target_ws, user_id=user.id, role=role, active=True)
        db.add(member)
    db.commit()
    return {
        'id': member.id,
        'user_id': user.id,
        'name': user.name,
        'email': user.email,
        'role': member.role,
        'workspace_id': target_ws,
        'workspace_name': ws_name,
        'isolated': isolated,
        'temporary_password': temp_pw,
    }


@router.put('/api/team/members/{member_id}/role')
def update_member_role(
    member_id: str,
    payload: RoleUpdateInput,
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    actor = context[1]
    role = payload.role.upper()
    if role not in {'ADMIN', 'MEMBER'}:
        raise HTTPException(422, 'Role must be ADMIN or MEMBER')
    target = db.get(WorkspaceMember, member_id)
    if not target or target.workspace_id != actor.workspace_id:
        raise HTTPException(404, 'Member not found in this workspace')
    if target.role == 'OWNER':
        raise HTTPException(409, 'Cannot downgrade Owner role')
    if actor.role != 'OWNER' and (not actor.can_manage_admins or role == 'ADMIN' or target.role == 'ADMIN'):
        raise HTTPException(403, 'Owner access or Admin delegation required to manage Admin roles')
    target.role = role
    if role != 'ADMIN':
        target.can_manage_admins = False
    db.commit()
    return {'id': target.id, 'role': target.role, 'workspace_id': target.workspace_id}


def _token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.strip().encode('utf-8')).hexdigest()


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _invite_status(inv: WorkspaceInvite, now: datetime | None = None) -> str:
    cur = now or datetime.now(timezone.utc)
    if inv.revoked:
        return 'revoked'
    if inv.used_at is not None:
        return 'used'
    if _as_utc(inv.expires_at) <= cur:
        return 'expired'
    return 'active'


def _serialize_invite(inv: WorkspaceInvite, workspace_name: str = '') -> dict:
    return {
        'id': inv.id,
        'workspace_id': inv.workspace_id,
        'workspace_name': workspace_name or inv.workspace_id,
        'role': inv.role,
        'isolated': bool(inv.isolated),
        'label': inv.label or '',
        'target_email': inv.target_email,
        'status': _invite_status(inv),
        'expires_at': _as_utc(inv.expires_at).isoformat(),
        'used_at': _as_utc(inv.used_at).isoformat() if inv.used_at else None,
        'created_at': _as_utc(inv.created_at).isoformat(),
    }


@router.get('/api/team/invites')
def list_invite_links(context=Depends(require_admin), db: Session = Depends(get_db)):
    actor = context[1]
    ws = db.get(Workspace, actor.workspace_id)
    ws_name = ws.name if ws else actor.workspace_id
    rows = (
        db.query(WorkspaceInvite)
        .filter_by(workspace_id=actor.workspace_id, revoked=False)
        .order_by(WorkspaceInvite.created_at.desc())
        .limit(50)
        .all()
    )
    return [_serialize_invite(row, ws_name) for row in rows]


@router.post('/api/team/invite-links', status_code=201)
def create_invite_link(
    payload: InviteLinkCreateInput,
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user, actor = context
    if payload.isolated or payload.role == 'ADMIN':
        if actor.role != 'OWNER' and not (not payload.isolated and actor.can_manage_admins):
            raise HTTPException(
                403,
                'Owner permission or admin delegation required for Admin / Isolated Friend invite links',
            )
    ws = db.get(Workspace, actor.workspace_id)
    ws_name = ws.name if ws else actor.workspace_id
    raw_token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    inv = WorkspaceInvite(
        id=new_id(),
        workspace_id=actor.workspace_id,
        created_by_user_id=user.id,
        token_hash=_token_digest(raw_token),
        role='ADMIN' if payload.isolated else payload.role,
        isolated=bool(payload.isolated),
        label=payload.label.strip(),
        target_email=payload.target_email.lower() if payload.target_email else None,
        expires_at=now + timedelta(days=payload.expires_in_days),
    )
    db.add(inv)
    db.add(
        AdminAudit(
            id=new_id(),
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            target_id=inv.id,
            action='invite_link_created',
            details=json.dumps({
                'role': inv.role,
                'isolated': inv.isolated,
                'target_email': inv.target_email,
            }),
        )
    )
    db.commit()
    db.refresh(inv)
    return {
        **_serialize_invite(inv, ws_name),
        'token': raw_token,
        'invite_path': f'/join?invite={raw_token}',
    }


@router.delete('/api/team/invites/{invite_id}')
def revoke_invite_link(invite_id: str, context=Depends(require_admin), db: Session = Depends(get_db)):
    actor = context[1]
    inv = db.get(WorkspaceInvite, invite_id)
    if not inv or inv.workspace_id != actor.workspace_id:
        raise HTTPException(404, 'Invite link not found')
    inv.revoked = True
    db.commit()
    return {'revoked': True, 'id': invite_id}


@router.get('/api/invites/{token}')
def preview_invite_link(token: str, db: Session = Depends(get_db)):
    inv = db.query(WorkspaceInvite).filter_by(token_hash=_token_digest(token)).first()
    if not inv or _invite_status(inv) != 'active':
        raise HTTPException(410, 'This invite link is invalid, already used, or expired.')
    ws = db.get(Workspace, inv.workspace_id)
    return {
        'valid': True,
        'workspace_name': 'Private Isolated Studio' if inv.isolated else (ws.name if ws else 'Studio Workspace'),
        'role': inv.role,
        'isolated': bool(inv.isolated),
        'label': inv.label or '',
        'target_email': inv.target_email,
        'expires_at': _as_utc(inv.expires_at).isoformat(),
    }


@router.post('/api/invites/accept', status_code=201)
def accept_invite_link(payload: InviteAcceptInput, db: Session = Depends(get_db)):
    inv = db.query(WorkspaceInvite).filter_by(token_hash=_token_digest(payload.token)).first()
    if not inv or _invite_status(inv) != 'active':
        raise HTTPException(410, 'This invite link is invalid, already used, or expired.')
    email = payload.email.lower()
    if inv.target_email and email != inv.target_email.lower():
        raise HTTPException(403, 'This invite link was issued for a different email address.')
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, 'An account with this email already exists. Sign in on the login page.')

    now = datetime.now(timezone.utc)
    clean_name = payload.name.strip()
    user = User(
        id=new_id(),
        name=clean_name,
        email=email,
        password_hash=hash_password(payload.password),
        email_verified_at=now,
    )
    db.add(user)
    db.flush()

    if inv.isolated:
        ws = Workspace(id=new_id(), name=f'{clean_name} Workspace')
        db.add(ws)
        db.flush()
        target_ws = ws.id
        member_role = 'ADMIN'
    else:
        target_ws = inv.workspace_id
        member_role = inv.role if inv.role in {'ADMIN', 'MEMBER'} else 'MEMBER'

    member = WorkspaceMember(
        id=new_id(),
        workspace_id=target_ws,
        user_id=user.id,
        role=member_role,
        active=True,
    )
    db.add(member)
    inv.used_at = now
    inv.used_by_user_id = user.id
    db.add(
        AdminAudit(
            id=new_id(),
            workspace_id=inv.workspace_id,
            actor_id=user.id,
            target_id=member.id,
            action='invite_link_accepted',
            details=json.dumps({
                'role': member_role,
                'isolated': bool(inv.isolated),
                'target_workspace_id': target_ws,
            }),
        )
    )
    db.commit()
    return {
        'access_token': create_token(user.id),
        'token_type': 'bearer',
        'user': {'id': user.id, 'name': user.name, 'email': user.email},
        'role': member.role,
        'workspace_id': target_ws,
    }

