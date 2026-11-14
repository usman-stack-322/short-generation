"""Studio APIs: Celebrity Vault, Scene Manual Upload, Review Queue, YouTube Upload, Workspaces & Team RBAC."""
import hashlib
import json
import os
import secrets
import shutil
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
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
    index_vault_files,
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


class UploadCheckItem(BaseModel):
    relative_path: str = Field(min_length=1, max_length=1000)
    size: int = Field(default=0, ge=0)


class UploadCheckInput(BaseModel):
    celebrity_name: str = Field(default='', max_length=160)
    items: list[UploadCheckItem] = Field(default_factory=list, max_length=2000)


class RescanFolderInput(BaseModel):
    preference: str | None = Field(default=None)


def _vault_root(db: Session, workspace_id: str) -> tuple[Path, CelebrityFolder | None]:
    folder_row = db.get(CelebrityFolder, workspace_id)
    if folder_row and Path(folder_row.folder_path).is_dir():
        root = Path(folder_row.folder_path).resolve()
    else:
        root = (Path(settings.generated_dir).resolve() / 'celebrity_vault' / workspace_id).resolve()
        root.mkdir(parents=True, exist_ok=True)
    return root, folder_row


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


def _resolve_vault_target(root: Path, raw_name: str, override_celebrity: str) -> Path | None:
    clean = (raw_name or 'asset').replace('\\', '/')
    orig = Path(clean)
    fname = Path(orig.name).name
    if not fname or fname.startswith('.tmp_'):
        return None
    if orig.suffix.lower() not in ALLOWED_EXTS:
        return None
    rel_sub = _safe_rel_subdir(orig, override_celebrity)
    target = (root / rel_sub / fname).resolve()
    if root not in target.parents:
        return None
    return target


def _scan_manifest_sizes(root: Path) -> dict[str, int]:
    """Fast recursive os.scandir walk returning lowercase relative path -> byte size."""
    files: dict[str, int] = {}
    root_str = str(root)
    stack = [root_str]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    name = entry.name
                    if name.startswith('.tmp_'):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            ext = os.path.splitext(name)[1].lower()
                            if ext not in ALLOWED_EXTS:
                                continue
                            sz = entry.stat(follow_symlinks=False).st_size
                            if sz > 0:
                                rel = os.path.relpath(entry.path, root_str).replace('\\', '/').lower()
                                files[rel] = sz
                    except OSError:
                        continue
        except OSError:
            continue
    return files


def _is_loopback_request(request: Request | None) -> bool:
    """True only when HTTP request came directly from the same local machine without remote proxy forwarding."""
    if request is None:
        return False
    if request.headers.get('x-forwarded-for') or request.headers.get('forwarded'):
        return False
    host = ((request.client.host if request.client else '') or '').strip().lower()
    return host in {'127.0.0.1', '::1', 'localhost'}


def _local_shortcuts() -> list[dict]:
    shortcuts: list[dict] = []
    if os.name == 'nt':
        try:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            get_type = ctypes.windll.kernel32.GetDriveTypeW
            for idx, letter in enumerate(string.ascii_uppercase):
                if not (mask & (1 << idx)):
                    continue
                drive = f'{letter}:\\'
                # Include fixed (3) and removable (2) drives without blocking on offline network shares
                if get_type(drive) in (2, 3):
                    shortcuts.append({'name': f'Drive ({letter}:)', 'path': drive, 'kind': 'drive'})
        except Exception:
            for letter in ('C', 'D', 'E', 'F'):
                drive = f'{letter}:\\'
                if os.path.isdir(drive):
                    shortcuts.append({'name': f'Drive ({letter}:)', 'path': drive, 'kind': 'drive'})
    else:
        shortcuts.append({'name': 'Root (/)', 'path': '/', 'kind': 'drive'})
    home = Path.home()
    for label in ('Desktop', 'Downloads', 'Documents', 'Videos', 'Pictures'):
        p = home / label
        try:
            if p.is_dir():
                shortcuts.append({'name': label, 'path': str(p), 'kind': 'home'})
        except OSError:
            continue
    return shortcuts


@router.get('/api/assets/local-browse')
def browse_local_folders(
    request: Request,
    path: str = '',
    context=Depends(require_admin),
):
    """Browse directories directly on the local machine for zero-copy 100GB+ folder linking."""
    if not _is_loopback_request(request):
        raise HTTPException(
            403,
            'Direct disk browsing is only available when the backend runs locally on this computer. Use People & Clips Sync to upload.',
        )
    shortcuts = _local_shortcuts()
    raw = path.strip()
    if not raw:
        return {
            'current_path': '',
            'parent_path': '',
            'folders': [s for s in shortcuts if s['kind'] == 'drive'],
            'shortcuts': shortcuts,
            'direct_media_count': 0,
        }

    target = Path(raw).expanduser()
    if os.name == 'nt' and len(raw) == 2 and raw[1] == ':':
        target = Path(raw + '\\')
    try:
        resolved = target.resolve()
    except OSError as exc:
        raise HTTPException(422, f'Invalid folder path: {exc}') from None
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(404, f'Folder not found: {resolved}')

    folders: list[dict] = []
    direct_media_count = 0
    try:
        with os.scandir(resolved) as it:
            for entry in it:
                name = entry.name
                if name.startswith('$') or name.startswith('.tmp_'):
                    continue
                if name.lower() in {'system volume information', 'recovery'}:
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not name.startswith('.'):
                            folders.append({'name': name, 'path': entry.path, 'kind': 'folder'})
                    elif entry.is_file(follow_symlinks=False):
                        if os.path.splitext(name)[1].lower() in ALLOWED_EXTS:
                            direct_media_count += 1
                except OSError:
                    continue
    except PermissionError:
        raise HTTPException(403, f'Permission denied reading folder: {resolved}') from None
    except OSError as exc:
        raise HTTPException(422, f'Unable to read folder: {exc}') from None

    folders.sort(key=lambda item: item['name'].lower())
    parent = str(resolved.parent) if resolved.parent != resolved else ''
    return {
        'current_path': str(resolved),
        'parent_path': parent,
        'folders': folders[:500],
        'shortcuts': shortcuts,
        'direct_media_count': direct_media_count,
    }


@router.get('/api/assets/manifest')
def get_vault_manifest(
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    root, _ = _vault_root(db, context[1].workspace_id)
    files = _scan_manifest_sizes(root)
    return {
        'folder_path': str(root),
        'total': len(files),
        'files': files,
    }


@router.post('/api/assets/check-existing')
def check_existing_vault_files(
    payload: UploadCheckInput,
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    root, _ = _vault_root(db, context[1].workspace_id)
    existing_indices: list[int] = []
    for idx, item in enumerate(payload.items):
        target = _resolve_vault_target(root, item.relative_path, payload.celebrity_name)
        if not target or not target.is_file():
            continue
        if item.size <= 0 or target.stat().st_size == item.size:
            existing_indices.append(idx)
    return {
        'existing_indices': existing_indices,
        'existing_count': len(existing_indices),
        'total': len(payload.items),
        'folder_path': str(root),
    }


@router.post('/api/assets/rescan')
def rescan_vault_folder(
    payload: RescanFolderInput | None = None,
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    workspace_id = context[1].workspace_id
    root, folder_row = _vault_root(db, workspace_id)
    pref = (payload.preference if payload else None) or (folder_row.preference if folder_row else 'mix_both')
    if pref not in {'mix_both', 'prefer_clips', 'prefer_images'}:
        pref = 'mix_both'
    return scan_celebrity_folder(db, workspace_id, str(root), pref)


@router.post('/api/assets/upload-bulk')
def upload_bulk(
    celebrity_name: str = Form(''),
    skip_scan: bool = Form(False),
    skip_existing: bool = Form(True),
    defer_index: bool = Form(False),
    files: list[UploadFile] = File(...),
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    workspace_id = context[1].workspace_id
    root, folder_row = _vault_root(db, workspace_id)
    should_defer_index = defer_index is True
    saved = 0
    skipped = 0
    saved_paths: list[Path] = []
    for f in files:
        try:
            out_path = _resolve_vault_target(root, f.filename or 'asset', celebrity_name)
            if not out_path:
                continue
            file_size = getattr(f, 'size', None) or 0
            if skip_existing and file_size > 0 and out_path.is_file() and out_path.stat().st_size == file_size:
                skipped += 1
                if not should_defer_index:
                    saved_paths.append(out_path)
                continue
            out_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = out_path.with_name(f'.tmp_{uuid4().hex[:8]}_{out_path.name}')
            try:
                with tmp_path.open('wb') as dst:
                    shutil.copyfileobj(f.file, dst, length=4 * 1024 * 1024)
                if tmp_path.stat().st_size == 0:
                    tmp_path.unlink(missing_ok=True)
                    continue
                os.replace(tmp_path, out_path)
                saved += 1
                if not should_defer_index:
                    saved_paths.append(out_path)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
        finally:
            try:
                f.file.close()
            except Exception:
                pass
    if saved == 0 and skipped == 0 and not skip_scan:
        raise HTTPException(422, 'No supported image (.jpg/.png/.webp) or video (.mp4/.mov/.webm) files uploaded.')
    if skip_scan:
        if saved_paths and not should_defer_index:
            index_vault_files(db, workspace_id, root, saved_paths)
        return {'saved': saved, 'skipped': skipped, 'scanning': False, 'folder_path': str(root)}
    summary = scan_celebrity_folder(db, workspace_id, str(root), folder_row.preference if folder_row else 'mix_both')
    return {**summary, 'saved': saved, 'skipped': skipped}


@router.post('/api/assets/upload-chunk')
def upload_vault_chunk(
    relative_path: str = Form(..., min_length=1, max_length=1000),
    celebrity_name: str = Form(''),
    upload_id: str = Form(..., min_length=4, max_length=80),
    chunk_index: int = Form(..., ge=0),
    total_chunks: int = Form(..., ge=1, le=50000),
    total_size: int = Form(..., ge=1),
    file: UploadFile = File(...),
    context=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Receive large video clips in resumable chunks so 100GB+ uploads work reliably without proxy timeouts."""
    workspace_id = context[1].workspace_id
    root, _ = _vault_root(db, workspace_id)
    out_path = _resolve_vault_target(root, relative_path, celebrity_name)
    if not out_path:
        try:
            file.file.close()
        except Exception:
            pass
        raise HTTPException(422, 'Unsupported media extension or invalid relative path.')

    if out_path.is_file() and out_path.stat().st_size == total_size:
        try:
            file.file.close()
        except Exception:
            pass
        index_vault_files(db, workspace_id, root, [out_path])
        return {'saved': 0, 'skipped': 1, 'completed': True, 'folder_path': str(root)}

    safe_id = ''.join(ch for ch in upload_id if ch.isalnum() or ch in '-_')[:64] or uuid4().hex
    stage_dir = root / '.tmp_chunks' / f'{workspace_id[:12]}_{safe_id}'
    stage_dir.mkdir(parents=True, exist_ok=True)
    chunk_file = stage_dir / f'c_{chunk_index:06d}'
    chunk_tmp = stage_dir / f'c_{chunk_index:06d}.tmp'
    try:
        with chunk_tmp.open('wb') as dst:
            shutil.copyfileobj(file.file, dst, length=4 * 1024 * 1024)
        os.replace(chunk_tmp, chunk_file)
    except Exception:
        chunk_tmp.unlink(missing_ok=True)
        raise
    finally:
        try:
            file.file.close()
        except Exception:
            pass

    all_chunks = [stage_dir / f'c_{idx:06d}' for idx in range(total_chunks)]
    if not all(p.is_file() for p in all_chunks):
        return {'saved': 0, 'skipped': 0, 'completed': False, 'chunk_index': chunk_index, 'folder_path': str(root)}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    assembled_tmp = out_path.with_name(f'.tmp_{uuid4().hex[:8]}_{out_path.name}')
    try:
        os.replace(all_chunks[0], assembled_tmp)
        if len(all_chunks) > 1:
            with assembled_tmp.open('ab') as out_dst:
                for part in all_chunks[1:]:
                    with part.open('rb') as src_part:
                        shutil.copyfileobj(src_part, out_dst, length=4 * 1024 * 1024)
        if assembled_tmp.stat().st_size <= 0:
            assembled_tmp.unlink(missing_ok=True)
            raise HTTPException(422, 'Uploaded chunked file was empty.')
        os.replace(assembled_tmp, out_path)
    except Exception:
        assembled_tmp.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

    index_vault_files(db, workspace_id, root, [out_path])
    return {'saved': 1, 'skipped': 0, 'completed': True, 'folder_path': str(root)}


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

