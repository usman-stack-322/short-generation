from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Celebrity, RenderJob, User, VideoProject
from ..schemas import (
    DeleteProjectResponse,
    ProjectCreate,
    ProjectOut,
    RenderJobOut,
    WorkerProgressUpdate,
)
from ..services.clip_matcher import CelebrityProfile, detect_celebrities
from ..services.r2_storage import R2StorageService
from .deps import get_current_user, get_current_user_from_header_or_query, verify_worker_token

router = APIRouter(prefix="/api/projects", tags=["projects"])
LOCAL_RENDERS_ROOT = Path("generated/renders")


def _to_job_out(job: Optional[RenderJob]) -> Optional[RenderJobOut]:
    if not job:
        return None
    return RenderJobOut(
        id=job.id,
        project_id=job.project_id,
        status=job.status,
        current_step=job.current_step,
        progress_pct=job.progress_pct,
        worker_id=job.worker_id,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _to_project_out(project: VideoProject, job: Optional[RenderJob]) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        owner_id=project.owner_id,
        mode=project.mode,
        input_type=project.input_type,
        title=project.title,
        raw_input=project.raw_input,
        final_script=project.final_script,
        detected_celebrities=json.loads(project.detected_celebrities_json or "[]"),
        voice_name=project.voice_name,
        target_duration_sec=project.target_duration_sec,
        status=project.status,
        output_r2_key=project.output_r2_key,
        created_at=project.created_at,
        latest_job=_to_job_out(job),
    )


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_user),
):
    celebs = db.execute(select(Celebrity).where(Celebrity.owner_id == owner.id)).scalars().all()
    catalog = [
        CelebrityProfile(
            id=c.id,
            name=c.name,
            slug=c.slug,
            aliases=json.loads(c.aliases_json or "[]"),
        )
        for c in celebs
    ]
    detected = detect_celebrities(f"{payload.title}\n{payload.raw_input}", catalog)

    project = VideoProject(
        owner_id=owner.id,
        mode=payload.mode,
        input_type=payload.input_type,
        title=payload.title.strip(),
        raw_input=payload.raw_input.strip(),
        final_script=payload.raw_input.strip() if payload.input_type == "script" else None,
        detected_celebrities_json=json.dumps([c.name for c in detected]),
        voice_name=payload.voice_name,
        target_duration_sec=payload.target_duration_sec,
        status="queued",
    )
    db.add(project)
    db.flush()

    job = RenderJob(
        project_id=project.id,
        owner_id=owner.id,
        status="queued",
        current_step="queued",
        progress_pct=0,
    )
    db.add(job)
    db.commit()
    db.refresh(project)
    db.refresh(job)

    return _to_project_out(project, job)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_user),
):
    projects = db.execute(
        select(VideoProject)
        .where(VideoProject.owner_id == owner.id)
        .order_by(VideoProject.created_at.desc())
        .limit(50)
    ).scalars().all()

    results: list[ProjectOut] = []
    for project in projects:
        latest_job = db.execute(
            select(RenderJob)
            .where(RenderJob.project_id == project.id)
            .order_by(RenderJob.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        results.append(_to_project_out(project, latest_job))
    return results


@router.post("/worker/claim", response_model=Optional[ProjectOut], dependencies=[Depends(verify_worker_token)])
def claim_next_job(
    worker_id: str = Query(default="local-pc-worker"),
    db: Session = Depends(get_db),
):
    """Option B Hybrid Endpoint: Your local PC worker polls this to claim queued cloud jobs."""
    job = db.execute(
        select(RenderJob)
        .where(RenderJob.status == "queued")
        .order_by(RenderJob.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if not job:
        return None

    project = db.execute(select(VideoProject).where(VideoProject.id == job.project_id)).scalar_one()
    job.status = "processing"
    job.current_step = "claimed"
    job.worker_id = worker_id
    job.started_at = datetime.now(timezone.utc)
    project.status = "processing"
    db.commit()
    db.refresh(project)
    db.refresh(job)
    return _to_project_out(project, job)


@router.post("/worker/jobs/{job_id}/progress", response_model=RenderJobOut, dependencies=[Depends(verify_worker_token)])
def update_job_progress(
    job_id: str,
    payload: WorkerProgressUpdate,
    db: Session = Depends(get_db),
):
    job = db.execute(select(RenderJob).where(RenderJob.id == job_id)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")

    project = db.execute(select(VideoProject).where(VideoProject.id == job.project_id)).scalar_one()
    job.current_step = payload.current_step
    job.progress_pct = payload.progress_pct
    job.status = payload.status
    project.status = payload.status

    if payload.final_script is not None:
        project.final_script = payload.final_script
    if payload.output_r2_key is not None:
        project.output_r2_key = payload.output_r2_key
    if payload.error_message is not None:
        job.error_message = payload.error_message
    if payload.status in ("completed", "failed"):
        job.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(job)
    return _to_job_out(job)


@router.get("/{project_id}/video")
def stream_project_video(
    project_id: str,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_user_from_header_or_query),
):
    """Stream or download the rendered MP4 (from local disk in STORAGE_MODE=local or R2 presigned URL)."""
    project = db.execute(
        select(VideoProject).where(VideoProject.id == project_id, VideoProject.owner_id == owner.id)
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.output_r2_key:
        raise HTTPException(status_code=404, detail="Rendered video is not available yet")

    if project.output_r2_key.startswith("local://"):
        raw_path = project.output_r2_key[len("local://"):]
        video_path = Path(raw_path)
        if not video_path.is_file():
            raise HTTPException(status_code=404, detail="Rendered video file not found on disk")
        return FileResponse(path=video_path, media_type="video/mp4", filename=f"{project.id}.mp4")

    settings = get_settings()
    if settings.is_local_storage:
        raise HTTPException(status_code=404, detail="Local video path expected in STORAGE_MODE=local")

    try:
        url = R2StorageService(settings=settings).generate_presigned_download_url(project.output_r2_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(url=url)


@router.delete("/{project_id}", response_model=DeleteProjectResponse)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_user),
):
    """Deletes a project (cascading its RenderJobs) and unlinks any local rendered MP4 inside generated/renders/."""
    project = db.execute(
        select(VideoProject).where(VideoProject.id == project_id, VideoProject.owner_id == owner.id)
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    renders_root = LOCAL_RENDERS_ROOT.resolve()
    if project.output_r2_key and project.output_r2_key.startswith("local://"):
        raw_path = project.output_r2_key[len("local://"):]
        try:
            target = Path(raw_path).resolve()
            if target.is_relative_to(renders_root) and target.suffix.lower() == ".mp4":
                target.unlink(missing_ok=True)
        except OSError:
            pass

    work_dir = (renders_root / f".work_{project.id}").resolve()
    if work_dir.is_relative_to(renders_root) and work_dir.is_dir():
        shutil.rmtree(work_dir, ignore_errors=True)

    db.delete(project)
    db.commit()
    return DeleteProjectResponse(deleted=True, project_id=project_id)
