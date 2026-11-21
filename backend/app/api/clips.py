from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bulk_sync_r2 import (
    VIDEO_EXTENSIONS,
    compute_fast_hash,
    extract_filename_tags,
    probe_video_metadata,
)

from .. import database
from ..config import get_settings
from ..database import get_db
from ..models import Celebrity, MediaClip, User
from ..schemas import (
    BulkIndexRequest,
    BulkIndexResponse,
    ClipOut,
    LocalUploadResponse,
    MarkClipsUsedRequest,
    MarkClipsUsedResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
    ScanLocalFolderRequest,
    ScanLocalFolderStatus,
)
from ..services.clip_matcher import slugify
from ..services.r2_storage import R2StorageService
from .deps import get_current_owner, verify_worker_token

router = APIRouter(prefix="/api/clips", tags=["clips"])
LOCAL_UPLOAD_ROOT = Path("generated/vault_uploads")


@router.get("", response_model=list[ClipOut])
def list_clips(
    celebrity_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
):
    stmt = (
        select(MediaClip, Celebrity.name)
        .join(Celebrity, Celebrity.id == MediaClip.celebrity_id)
        .where(MediaClip.owner_id == owner.id)
        .order_by(MediaClip.created_at.desc())
        .limit(limit)
    )
    if celebrity_id:
        stmt = stmt.where(MediaClip.celebrity_id == celebrity_id)

    rows = db.execute(stmt).all()
    return [
        ClipOut(
            id=clip.id,
            celebrity_id=clip.celebrity_id,
            celebrity_name=celeb_name,
            r2_key=clip.r2_key,
            filename=clip.filename,
            file_size_bytes=clip.file_size_bytes,
            duration_sec=clip.duration_sec,
            width=clip.width,
            height=clip.height,
            aspect_ratio=clip.aspect_ratio,
            source_type=clip.source_type,
            tags=json.loads(clip.tags_json or "[]"),
            usage_count=clip.usage_count,
            created_at=clip.created_at,
        )
        for clip, celeb_name in rows
    ]


@router.post("/presign-upload", response_model=PresignedUploadResponse)
def create_presigned_upload(
    payload: PresignedUploadRequest,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
):
    celeb = db.execute(
        select(Celebrity).where(Celebrity.id == payload.celebrity_id, Celebrity.owner_id == owner.id)
    ).scalar_one_or_none()
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")

    ext = Path(payload.filename).suffix.lower() or ".mp4"
    r2_key = f"vault/{owner.id}/{celeb.slug}/{uuid.uuid4().hex}{ext}"

    storage = R2StorageService()
    try:
        upload_url = storage.generate_presigned_upload_url(r2_key=r2_key, content_type=payload.content_type)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return PresignedUploadResponse(r2_key=r2_key, upload_url=upload_url, expires_in_sec=3600)


@router.post("/bulk-index", response_model=BulkIndexResponse)
def bulk_index_clips(
    payload: BulkIndexRequest,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
):
    """Used by scripts/bulk_sync_r2.py to register hundreds of R2 clips in one batch."""
    inserted = 0
    skipped = 0
    celebs_created = 0

    celeb_cache: dict[str, Celebrity] = {
        c.slug: c
        for c in db.execute(select(Celebrity).where(Celebrity.owner_id == owner.id)).scalars().all()
    }
    existing_hashes = set(
        db.execute(select(MediaClip.file_hash).where(MediaClip.owner_id == owner.id)).scalars().all()
    )
    existing_r2_keys = set(
        db.execute(select(MediaClip.r2_key)).scalars().all()
    )

    for item in payload.clips:
        if item.file_hash in existing_hashes or item.r2_key in existing_r2_keys:
            skipped += 1
            continue

        slug = slugify(item.celebrity_name)
        celeb = celeb_cache.get(slug)
        if celeb is None:
            celeb = Celebrity(
                owner_id=owner.id,
                name=item.celebrity_name.strip(),
                slug=slug,
                category=item.category,
                aliases_json="[]",
            )
            db.add(celeb)
            db.flush()
            celeb_cache[slug] = celeb
            celebs_created += 1

        clip = MediaClip(
            owner_id=owner.id,
            celebrity_id=celeb.id,
            r2_key=item.r2_key,
            filename=item.filename,
            file_hash=item.file_hash,
            file_size_bytes=item.file_size_bytes,
            duration_sec=item.duration_sec,
            width=item.width,
            height=item.height,
            aspect_ratio=item.aspect_ratio,
            source_type=item.source_type,
            source_url=item.source_url,
            tags_json=json.dumps(item.tags),
        )
        db.add(clip)
        existing_hashes.add(item.file_hash)
        existing_r2_keys.add(item.r2_key)
        inserted += 1

    db.commit()
    return BulkIndexResponse(
        inserted=inserted,
        skipped_existing=skipped,
        celebrities_created=celebs_created,
    )


@router.post("/worker/mark-used", response_model=MarkClipsUsedResponse, dependencies=[Depends(verify_worker_token)])
def mark_clips_used(
    payload: MarkClipsUsedRequest,
    db: Session = Depends(get_db),
):
    """Increment usage_count after a successful render so future timelines rotate vault clips."""
    unique_ids = list(dict.fromkeys(cid.strip() for cid in payload.clip_ids if cid and cid.strip()))
    if not unique_ids:
        return MarkClipsUsedResponse(updated=0)

    clips = db.execute(select(MediaClip).where(MediaClip.id.in_(unique_ids))).scalars().all()
    now = datetime.now(timezone.utc)
    for clip in clips:
        clip.usage_count = int(clip.usage_count or 0) + 1
        clip.last_used_at = now
    db.commit()
    return MarkClipsUsedResponse(updated=len(clips))


@router.post("/upload-local", response_model=LocalUploadResponse)
def upload_local_clips(
    celebrity_id: str = Form(...),
    files: list[UploadFile] = File(...),
    tags: str = Form(default=""),
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
):
    """Uploads 1-5 clips directly from the browser into generated/vault_uploads/ in STORAGE_MODE=local."""
    settings = get_settings()
    if not settings.is_local_storage:
        raise HTTPException(
            status_code=400,
            detail="Direct local upload is only enabled when STORAGE_MODE=local. Use /api/clips/presign-upload for R2.",
        )
    if not files or len(files) > 5:
        raise HTTPException(status_code=400, detail="Select between 1 and 5 video files per upload.")

    celeb = db.execute(
        select(Celebrity).where(Celebrity.id == celebrity_id, Celebrity.owner_id == owner.id)
    ).scalar_one_or_none()
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")

    target_dir = LOCAL_UPLOAD_ROOT / celeb.slug
    target_dir.mkdir(parents=True, exist_ok=True)

    existing_hashes = set(
        db.execute(select(MediaClip.file_hash).where(MediaClip.owner_id == owner.id)).scalars().all()
    )
    existing_r2_keys = set(db.execute(select(MediaClip.r2_key)).scalars().all())
    custom_tags = [re.sub(r"[^a-z0-9_-]+", "", t.strip().lower()) for t in tags.split(",") if t.strip()]
    custom_tags = [t for t in custom_tags if t]

    created: list[ClipOut] = []
    skipped = 0

    for upload in files:
        orig_name = Path(upload.filename or "clip.mp4").name
        ext = Path(orig_name).suffix.lower()
        if ext not in VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{orig_name}'. Allowed: {', '.join(sorted(VIDEO_EXTENSIONS))}",
            )

        safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(orig_name).stem).strip("_") or "clip"
        dest = target_dir / f"{safe_stem}{ext}"
        if dest.exists():
            dest = target_dir / f"{safe_stem}_{uuid.uuid4().hex[:8]}{ext}"

        try:
            with dest.open("wb") as out_f:
                shutil.copyfileobj(upload.file, out_f)
        finally:
            upload.file.close()

        file_hash = compute_fast_hash(dest)
        r2_key = f"local://{dest.resolve().as_posix()}"

        if file_hash in existing_hashes or r2_key in existing_r2_keys:
            dest.unlink(missing_ok=True)
            skipped += 1
            continue

        duration_sec, width, height, aspect_ratio = probe_video_metadata(dest)
        merged_tags = sorted(set(custom_tags + extract_filename_tags(orig_name)))[:12]

        clip = MediaClip(
            owner_id=owner.id,
            celebrity_id=celeb.id,
            r2_key=r2_key,
            filename=orig_name,
            file_hash=file_hash,
            file_size_bytes=dest.stat().st_size,
            duration_sec=duration_sec,
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            source_type="vault_upload",
            tags_json=json.dumps(merged_tags),
        )
        db.add(clip)
        db.flush()
        existing_hashes.add(file_hash)
        existing_r2_keys.add(r2_key)
        created.append(
            ClipOut(
                id=clip.id,
                celebrity_id=clip.celebrity_id,
                celebrity_name=celeb.name,
                r2_key=clip.r2_key,
                filename=clip.filename,
                file_size_bytes=clip.file_size_bytes,
                duration_sec=clip.duration_sec,
                width=clip.width,
                height=clip.height,
                aspect_ratio=clip.aspect_ratio,
                source_type=clip.source_type,
                tags=merged_tags,
                usage_count=clip.usage_count,
                created_at=clip.created_at,
            )
        )

    db.commit()
    return LocalUploadResponse(uploaded=len(created), skipped_existing=skipped, clips=created)


_SCAN_LOCK = threading.Lock()
_SCAN_JOBS: dict[str, dict] = {}
BULK_BATCH_SIZE = 500


def _snapshot_scan_job(job: dict) -> ScanLocalFolderStatus:
    return ScanLocalFolderStatus(
        scan_id=job["scan_id"],
        folder_path=job["folder_path"],
        category=job["category"],
        status=job["status"],
        total_files_found=job["total_files_found"],
        processed_files=job["processed_files"],
        inserted=job["inserted"],
        skipped_existing=job["skipped_existing"],
        celebrities_created=job["celebrities_created"],
        elapsed_ms=job["elapsed_ms"],
        current_celebrity=job["current_celebrity"],
        error_message=job["error_message"],
    )


def _fast_stat_hash(normalized_path: str, file_size: int, mtime_ns: int) -> str:
    """Instant deterministic fingerprint from normalized path + size + mtime_ns (0 video bytes read)."""
    return hashlib.sha256(f"{normalized_path}|{file_size}|{mtime_ns}".encode("utf-8")).hexdigest()


def _discover_local_videos(root_dir: Path) -> list[tuple[str, str, str, str, int, int]]:
    """Fast iterative os.scandir() traversal reading cached DirEntry stats without ffprobe or Path.rglob."""
    discovered: list[tuple[str, str, str, str, int, int]] = []
    root_str = str(root_dir.resolve())

    with os.scandir(root_str) as top_entries:
        celeb_entries = sorted(
            (e for e in top_entries if e.is_dir(follow_symlinks=False)),
            key=lambda e: e.name.lower(),
        )

    for celeb_entry in celeb_entries:
        celeb_name = celeb_entry.name.strip()
        if not celeb_name:
            continue
        celeb_slug = slugify(celeb_name)
        dir_stack = [celeb_entry.path]
        celeb_files: list[tuple[str, str, int, int]] = []

        while dir_stack:
            current_dir = dir_stack.pop()
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        dir_stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        if os.path.splitext(entry.name)[1].lower() not in VIDEO_EXTENSIONS:
                            continue
                        st = entry.stat(follow_symlinks=False)
                        norm_path = entry.path.replace("\\", "/")
                        celeb_files.append((norm_path, entry.name, st.st_size, st.st_mtime_ns))

        celeb_files.sort(key=lambda item: item[0])
        for norm_path, filename, file_size, mtime_ns in celeb_files:
            discovered.append((celeb_name, celeb_slug, norm_path, filename, file_size, mtime_ns))

    return discovered


def _run_local_folder_scan(
    scan_id: str,
    root_dir: Path,
    category: str,
    owner_id: str,
    probe_metadata: bool = False,
) -> None:
    """High-speed background indexer (<root_dir>/<Celebrity Name>/**/*) with bulk DB batching."""
    started = time.perf_counter()
    db: Optional[Session] = None
    final_status = "completed"
    err_msg: Optional[str] = None

    try:
        discovered = _discover_local_videos(root_dir)
        with _SCAN_LOCK:
            job = _SCAN_JOBS.get(scan_id)
            if job is not None:
                job["total_files_found"] = len(discovered)

        db = database.SessionLocal()
        celeb_id_by_slug: dict[str, str] = {
            slug: cid
            for slug, cid in db.execute(
                select(Celebrity.slug, Celebrity.id).where(Celebrity.owner_id == owner_id)
            ).all()
        }

        existing_hashes: set[str] = set()
        existing_r2_keys: set[str] = set()
        for row_owner_id, row_hash, row_r2_key in db.execute(
            select(MediaClip.owner_id, MediaClip.file_hash, MediaClip.r2_key)
        ).all():
            existing_r2_keys.add(row_r2_key)
            if row_owner_id == owner_id:
                existing_hashes.add(row_hash)

        clean_category = category.strip() or "NBA"
        new_celebrities: list[Celebrity] = []
        new_clips: list[MediaClip] = []
        skipped_count = 0

        for idx, (celeb_name, celeb_slug, norm_path, filename, file_size, mtime_ns) in enumerate(discovered, start=1):
            if idx == 1 or idx % 50 == 0:
                with _SCAN_LOCK:
                    job = _SCAN_JOBS.get(scan_id)
                    if job is not None:
                        job["current_celebrity"] = celeb_name

            r2_key = f"local://{norm_path}"
            file_hash = _fast_stat_hash(norm_path, file_size, mtime_ns)
            if r2_key in existing_r2_keys or file_hash in existing_hashes:
                skipped_count += 1
                continue

            celeb_id = celeb_id_by_slug.get(celeb_slug)
            if celeb_id is None:
                celeb_id = str(uuid.uuid4())
                celeb_id_by_slug[celeb_slug] = celeb_id
                new_celebrities.append(
                    Celebrity(
                        id=celeb_id,
                        owner_id=owner_id,
                        name=celeb_name,
                        slug=celeb_slug,
                        category=clean_category,
                        aliases_json="[]",
                    )
                )

            if probe_metadata:
                duration_sec, width, height, aspect_ratio = probe_video_metadata(Path(norm_path))
            else:
                duration_sec, width, height, aspect_ratio = 0.0, 0, 0, "16:9"

            new_clips.append(
                MediaClip(
                    owner_id=owner_id,
                    celebrity_id=celeb_id,
                    r2_key=r2_key,
                    filename=filename,
                    file_hash=file_hash,
                    file_size_bytes=file_size,
                    duration_sec=duration_sec,
                    width=width,
                    height=height,
                    aspect_ratio=aspect_ratio,
                    source_type="vault_upload",
                    tags_json=json.dumps(extract_filename_tags(filename)),
                )
            )
            existing_hashes.add(file_hash)
            existing_r2_keys.add(r2_key)

        if skipped_count:
            with _SCAN_LOCK:
                job = _SCAN_JOBS.get(scan_id)
                if job is not None:
                    job["skipped_existing"] = skipped_count
                    job["processed_files"] = skipped_count

        if new_celebrities:
            for start in range(0, len(new_celebrities), BULK_BATCH_SIZE):
                chunk = new_celebrities[start : start + BULK_BATCH_SIZE]
                db.add_all(chunk)
            db.flush()
            with _SCAN_LOCK:
                job = _SCAN_JOBS.get(scan_id)
                if job is not None:
                    job["celebrities_created"] = len(new_celebrities)

        if new_clips:
            for start in range(0, len(new_clips), BULK_BATCH_SIZE):
                chunk = new_clips[start : start + BULK_BATCH_SIZE]
                db.add_all(chunk)
                db.commit()
                with _SCAN_LOCK:
                    job = _SCAN_JOBS.get(scan_id)
                    if job is not None:
                        job["inserted"] += len(chunk)
                        job["processed_files"] = skipped_count + job["inserted"]
        elif new_celebrities:
            db.commit()
    except Exception as exc:
        final_status = "failed"
        err_msg = str(exc)[:1000]
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            db.close()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        with _SCAN_LOCK:
            job = _SCAN_JOBS.get(scan_id)
            if job is not None:
                job["elapsed_ms"] = elapsed_ms
                job["status"] = final_status
                job["current_celebrity"] = None
                job["error_message"] = err_msg


@router.post("/scan-local-folder", response_model=ScanLocalFolderStatus, status_code=202)
def start_local_folder_scan(
    payload: ScanLocalFolderRequest,
    owner: User = Depends(get_current_owner),
):
    """Starts a fast non-blocking background scan of <folder_path>/<Celebrity Name>/**/* when STORAGE_MODE=local."""
    settings = get_settings()
    if not settings.is_local_storage:
        raise HTTPException(
            status_code=400,
            detail="Local folder scanning is only available when STORAGE_MODE=local.",
        )

    cleaned_path = payload.folder_path.strip().strip('"').strip("'").strip()
    if not cleaned_path:
        raise HTTPException(status_code=400, detail="Folder path cannot be empty.")

    root_dir = Path(cleaned_path)
    if not root_dir.exists() or not root_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder does not exist on disk: {cleaned_path}")

    scan_id = uuid.uuid4().hex
    clean_category = payload.category.strip() or "NBA"
    job = {
        "scan_id": scan_id,
        "owner_id": owner.id,
        "folder_path": str(root_dir),
        "category": clean_category,
        "status": "running",
        "total_files_found": 0,
        "processed_files": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "celebrities_created": 0,
        "elapsed_ms": 0.0,
        "current_celebrity": None,
        "error_message": None,
    }
    with _SCAN_LOCK:
        if len(_SCAN_JOBS) > 50:
            oldest_key = next(iter(_SCAN_JOBS))
            _SCAN_JOBS.pop(oldest_key, None)
        _SCAN_JOBS[scan_id] = job
        snapshot = _snapshot_scan_job(job)

    worker = threading.Thread(
        target=_run_local_folder_scan,
        args=(scan_id, root_dir, clean_category, owner.id, payload.probe_metadata),
        daemon=True,
    )
    worker.start()
    return snapshot


@router.get("/scan-local-folder/{scan_id}", response_model=ScanLocalFolderStatus)
def get_local_folder_scan_status(
    scan_id: str,
    owner: User = Depends(get_current_owner),
):
    """Returns live progress counters for a running or finished local folder scan."""
    with _SCAN_LOCK:
        job = _SCAN_JOBS.get(scan_id)
        if not job or job.get("owner_id") != owner.id:
            raise HTTPException(status_code=404, detail="Folder scan job not found")
        return _snapshot_scan_job(job)
