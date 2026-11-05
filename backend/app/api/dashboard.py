from pathlib import Path
from datetime import datetime,timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import current_context
from app.database.session import get_db
from app.models import Channel, Personality, VideoJob, WorkspaceMember, UploadTask
from app.services.pipeline import serialize_job


from app.api.access import _accessible_channel_ids,personality_visible
router = APIRouter()
generated_dir = Path(settings.generated_dir).resolve()

@router.get("/api/dashboard")
def dashboard(context=Depends(current_context), db: Session = Depends(get_db)):
    user, membership = context
    visible_ids = _accessible_channel_ids(db, membership)
    channels_q = db.query(Channel).filter_by(workspace_id=membership.workspace_id)
    if visible_ids is not None:
        channels_q = channels_q.filter(Channel.id.in_(visible_ids))
    channels = channels_q.all()
    jobs_query = db.query(VideoJob).filter(VideoJob.workspace_id == membership.workspace_id)
    if visible_ids is not None:
        jobs_query = jobs_query.filter(VideoJob.channel_id.in_(visible_ids))
    all_jobs=jobs_query.all()
    today=datetime.now(timezone.utc).date()
    rows = jobs_query.order_by(VideoJob.created_at.desc()).limit(6).all()
    counts = {key: 0 for key in ("videos_generated", "waiting_approval", "uploaded", "failed")}
    for job in jobs_query.all():
        if job.video is not None:
            counts["videos_generated"] += 1
        if job.status == "ready_for_review":
            counts["waiting_approval"] += 1
        if job.status == "uploaded":
            counts["uploaded"] += 1
        if job.status in {"failed","upload_failed"}:
            counts["failed"] += 1
    members_count = db.query(WorkspaceMember).filter_by(workspace_id=membership.workspace_id).count()
    personalities = db.query(Personality).filter_by(workspace_id=membership.workspace_id, enabled=True).all()
    if visible_ids is not None:
        personalities = [p for p in personalities if personality_visible(p,membership,visible_ids)]
    team_activity=[]
    if membership.role=='OWNER':
        for member in db.query(WorkspaceMember).filter_by(workspace_id=membership.workspace_id):
            owned=[c for c in channels if c.member_id==member.id]
            jobs=[j for j in all_jobs if j.channel_id in {c.id for c in owned}]
            latest=max((j.updated_at for j in jobs),default=None)
            team_activity.append({'member':member.user.name,'channels':[c.name for c in owned],
                'videos_today':sum(j.video is not None and j.created_at.date()==today for j in jobs),
                'current_jobs':sum(j.status in {'researching','script_generation','collecting_assets','voice_generation','rendering','creating_cover'} for j in jobs),
                'failed_jobs':sum(j.status in {'failed','upload_failed'} for j in jobs),
                'recent_activity':latest.isoformat()+'Z' if latest else None,
                'last_active':member.last_active_at.isoformat()+'Z' if member.last_active_at else None})
    return {
        'processing':sum(j.status in {'researching','script_generation','collecting_assets','voice_generation','rendering','creating_cover','uploading'} for j in all_jobs),
        'needs_attention':sum(j.status in {'failed','upload_failed','verification_required'} for j in all_jobs),
        'scheduled_today':db.query(UploadTask).join(VideoJob).filter(VideoJob.id.in_([j.id for j in all_jobs]),UploadTask.status=='scheduled',UploadTask.scheduled_at>=datetime.combine(today,datetime.min.time()),UploadTask.scheduled_at<datetime.combine(today,datetime.max.time())).count(),
        'next_upload':next((t.scheduled_at.isoformat()+'Z' for t in db.query(UploadTask).join(VideoJob).filter(VideoJob.id.in_([j.id for j in all_jobs]),UploadTask.status=='scheduled',UploadTask.scheduled_at>=datetime.now(timezone.utc)).order_by(UploadTask.scheduled_at) if t.scheduled_at),None),
        'automation_state':'Automation enabled - setup pending' if any(c.automatic_generation_enabled for c in channels) and not any(c.status=='connected' and any(p.channel_id==c.id for p in personalities) for c in channels) else 'Preparation enabled; publishing requires approval' if any(c.automatic_generation_enabled for c in channels) else 'Manual preparation; publishing requires approval',
        'run_sheet':[serialize_job(j,db) for j in sorted(all_jobs,key=lambda j:j.updated_at,reverse=True)[:30]],
        "user": user.name, "role": membership.role, "total_channels": len(channels),
        **({'total_members':members_count,'team_activity':team_activity} if membership.role=='OWNER' else {}), **counts,
        'waiting_verification':sum(j.status=='verification_required' for j in all_jobs),
        'approved':sum(j.status=='approved' for j in all_jobs),
        "connected_channels":sum(c.status=='connected' for c in channels),
        "videos_today":sum(j.video is not None and j.created_at.date()==today for j in all_jobs),
        "scheduled":sum(j.status=='scheduled' for j in all_jobs),
        "day_timezone":"UTC",
        "channels": [{"id":c.id,"name":c.name,"status":c.status,"member_id":c.member_id,
            "member_name":c.member.user.name if c.member else 'Workspace owner',"profile_image_url":c.profile_image_url,
            "active_personality":next((p.name for p in personalities if p.channel_id==c.id and p.enabled),None),
            "daily_video_target":c.daily_video_target,"approval_policy":c.approval_policy,
            "videos_today":sum(j.channel_id==c.id and j.video is not None and j.created_at.date()==today for j in all_jobs),
            "next_scheduled":next((t.scheduled_at.isoformat()+'Z' for t in db.query(UploadTask).join(VideoJob).filter(VideoJob.channel_id==c.id,UploadTask.status=='scheduled').order_by(UploadTask.scheduled_at).all() if t.scheduled_at),None)} for c in channels],
        "active_personalities": [{"id": p.id, "name": p.name, "category": p.category} for p in personalities],
        "recent_videos": [serialize_job(job, db) for job in rows],
    }


