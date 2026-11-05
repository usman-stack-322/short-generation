from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.security import require_editor, new_id
from app.core.config import settings
from app.database.session import get_db
from app.models import UploadTask, Channel, Analytics
from app.schemas import PublishInput, InputModel
from pydantic import Field
from app.youtube.permissions import job_access, approve, approval_satisfied
from app.youtube.upload import upload_guard

router=APIRouter(prefix='/api/videos',tags=['Publishing'])


def run_requested_upload(task_id):
    from app.database.session import SessionLocal
    from app.youtube.upload import process_upload
    with SessionLocal() as db:
        task=db.get(UploadTask,task_id)
        if task:process_upload(db,task)


def queue_upload(db,job,member,payload,schedule=False):
    if not settings.youtube_uploads_enabled:
        raise HTTPException(409,'YouTube uploads are disabled by the platform operator. Your MP4 and exports remain available.')
    if schedule or payload.scheduled_at:
        raise HTTPException(422,'Upload privately now; publish or schedule manually in YouTube Studio')
    if payload.content_revision!=job.content_revision:
        raise HTTPException(409,'Review version changed. Refresh before publishing.')
    if not payload.confirmed:
        raise HTTPException(422,'Explicit final publishing confirmation is required')
    if job.status not in {'approved','upload_failed'}:
        raise HTTPException(409,'Approve this video before uploading or scheduling')
    channel=db.get(Channel,job.channel_id)
    if not approval_satisfied(db,job,channel):
        raise HTTPException(409,'The required approvers have not approved this content revision')
    task=db.query(UploadTask).filter_by(job_id=job.id).first()
    if task and (task.youtube_video_id or task.status in {'uploaded','uploading','upload_uncertain','pending','scheduled','processing','visibility_verification_failed','processing_failed'}):
        raise HTTPException(409,'Upload already exists or needs reconciliation. Duplicate upload prevented.')
    when=None
    if schedule:
        try:
            zone=ZoneInfo(payload.timezone)
            when=datetime.fromisoformat((payload.scheduled_at or '').replace('Z','+00:00'))
            if when.tzinfo is None:
                raise ValueError('Include the UTC offset in scheduled_at')
            # Store the UTC instant plus the chosen IANA timezone. Reject mismatched DST offsets.
            if when.utcoffset()!=when.astimezone(zone).utcoffset():
                raise ValueError('Schedule offset does not match selected timezone')
            when=when.astimezone(timezone.utc)
            if when<=datetime.now(timezone.utc):
                raise ValueError('Schedule must be in the future')
            import json
            defaults=json.loads(channel.operational_defaults or '{}')
            if defaults:
                local=when.astimezone(ZoneInfo(defaults.get('timezone','UTC')))
                if not defaults.get('posting_start',0)<=local.hour<defaults.get('posting_end',24):
                    raise ValueError('Outside channel posting window')
                from datetime import timedelta
                gap=timedelta(minutes=defaults.get('minimum_gap_minutes',0))
                from app.models import VideoJob
                others=db.query(UploadTask).join(VideoJob).filter(VideoJob.channel_id==channel.id,VideoJob.id!=job.id,UploadTask.status.in_(['scheduled','pending','uploading','uploaded'])).all()
                if any(t.scheduled_at and abs((when-t.scheduled_at.replace(tzinfo=timezone.utc)).total_seconds())<gap.total_seconds() for t in others):
                    raise ValueError('Channel minimum posting gap conflicts with another schedule')
        except (ValueError,ZoneInfoNotFoundError):
            raise HTTPException(422,'Use a future ISO date/time with matching UTC offset and IANA timezone, within the channel posting window and minimum gap') from None
    if not task:
        task=UploadTask(id=new_id(),job_id=job.id,requested_by=member.id,content_revision=job.content_revision,status='pending')
        db.add(task)
    task.requested_by,task.content_revision=member.id,job.content_revision
    task.privacy_status,task.made_for_kids='private',payload.made_for_kids
    task.scheduled_at,task.timezone=when,payload.timezone
    task.error_message=None
    task.progress=0
    task.resumable_uri_encrypted=None
    previous=job.status
    job.status='approved'
    try:
        upload_guard(db,job,task)
    except RuntimeError as exc:
        job.status=previous
        db.rollback()
        raise HTTPException(409,str(exc)) from None
    task.status='scheduled' if schedule else 'pending'
    task.retry_count=(task.retry_count or 0)+1
    job.status=job.current_step='scheduled' if schedule else 'approved'
    job.error_message=None
    db.commit()
    return {'id':task.id,'status':task.status,'scheduled_at':when.isoformat() if when else None,
            'uploads_enabled':settings.youtube_uploads_enabled}


@router.post('/{job_id}/upload')
def upload_video(job_id:str,payload:PublishInput,background:BackgroundTasks,context=Depends(require_editor),db:Session=Depends(get_db)):
    job=job_access(db,job_id,context[1],True)
    if payload.scheduled_at:
        raise HTTPException(422,'Use the schedule endpoint for future uploads')
    result=queue_upload(db,job,context[1],payload)
    background.add_task(run_requested_upload,result['id'])
    return result


@router.post('/{job_id}/resume-upload')
def resume_upload(job_id:str,background:BackgroundTasks,context=Depends(require_editor),db:Session=Depends(get_db)):
    if not settings.youtube_uploads_enabled:raise HTTPException(409,'YouTube uploads disabled')
    job=job_access(db,job_id,context[1],True)
    task=db.query(UploadTask).filter_by(job_id=job.id,status='pending',requested_by=context[1].id).first()
    if not task or task.youtube_video_id or task.resumable_uri_encrypted:raise HTTPException(409,'Only an unsent pending job can be resumed')
    background.add_task(run_requested_upload,task.id)
    return {'status':'pending'}


@router.post('/{job_id}/approve-upload')
def approve_upload(job_id:str,payload:PublishInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    raise HTTPException(422,'Approve the reviewed video first, then explicitly choose Upload Privately to YouTube')
    if not payload.confirmed:
        raise HTTPException(422,'Final confirmation required')
    job=job_access(db,job_id,context[1],True)
    approve(db,job,context[1],payload.content_revision)
    return queue_upload(db,job,context[1],payload)


@router.post('/{job_id}/schedule')
def schedule_video(job_id:str,payload:PublishInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    return queue_upload(db,job_access(db,job_id,context[1],True),context[1],payload,True)


@router.post('/{job_id}/cancel-schedule')
def cancel(job_id:str,context=Depends(require_editor),db:Session=Depends(get_db)):
    job=job_access(db,job_id,context[1],True)
    task=db.query(UploadTask).filter_by(job_id=job.id).first()
    if not task or task.status not in {'scheduled','pending'}:
        raise HTTPException(409,'No cancellable schedule exists')
    task.status='cancelled'
    job.status=job.current_step='approved'
    db.commit()
    return {'status':'cancelled'}


class ReconcileInput(InputModel):
    youtube_video_id: str | None = Field(default=None,pattern=r'^[A-Za-z0-9_-]{11}$')
    confirmed_absent: bool = False


@router.post('/{job_id}/verify-upload')
def verify(job_id:str,context=Depends(require_editor),db:Session=Depends(get_db)):
    from app.youtube.upload import verify_upload
    job=job_access(db,job_id,context[1],True)
    task=db.query(UploadTask).filter_by(job_id=job.id).first()
    if not task or not task.youtube_video_id:raise HTTPException(409,'No returned video ID to verify')
    if task.status=='uploaded':return {'status':task.status}
    verify_upload(db,job,task)
    return {'status':task.status}


@router.post('/{job_id}/reconcile-upload')
def reconcile(job_id:str,payload:ReconcileInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    from app.youtube.oauth import youtube,credentials_for
    job=job_access(db,job_id,context[1],True)
    task=db.query(UploadTask).filter_by(job_id=job.id).first()
    if not task or task.status!='upload_uncertain':
        raise HTTPException(409,'Only an interrupted, uncertain upload needs reconciliation')
    if payload.youtube_video_id:
        channel=db.get(Channel,job.channel_id)
        try:
            result=youtube(credentials_for(db,channel)).videos().list(part='snippet,status',id=payload.youtube_video_id).execute()
            item=result['items'][0]
            if item.get('status',{}).get('privacyStatus')!='private':
                raise ValueError('Private visibility could not be verified')
            if item['snippet']['channelId']!=channel.youtube_channel_id or item['snippet']['title']!=job.script.seo.title:
                raise ValueError('Channel or title mismatch')
        except Exception:
            raise HTTPException(409,'Could not verify that video against this channel and title') from None
        task.youtube_video_id=payload.youtube_video_id
        task.youtube_url='https://www.youtube.com/watch?v='+payload.youtube_video_id
        task.uploaded_at=datetime.now(timezone.utc)
        task.status,task.progress='processing',1
        job.status=job.current_step='processing'
    elif payload.confirmed_absent:
        # A person must check Studio; absence cannot reliably be inferred after a lost response.
        task.status='upload_failed'
        task.error_message='User confirmed no matching video exists in YouTube Studio. A new final confirmation is required to retry.'
    else:
        raise HTTPException(422,'Provide the existing YouTube video ID or explicitly confirm absence after checking Studio')
    task.resumable_uri_encrypted=None
    if task.status=='uploaded': task.error_message=job.error_message=None
    db.commit()
    if task.youtube_video_id:
        from app.youtube.upload import verify_upload
        verify_upload(db,job,task)
    return {'status':task.status,'youtube_url':task.youtube_url}


@router.post('/{job_id}/analytics/sync')
def analytics(job_id:str,context=Depends(require_editor),db:Session=Depends(get_db)):
    from app.youtube.oauth import youtube,credentials_for
    job=job_access(db,job_id,context[1])
    task=db.query(UploadTask).filter_by(job_id=job.id,status='uploaded').first()
    if not task:
        raise HTTPException(409,'Upload this video before syncing analytics')
    try:
        data=youtube(credentials_for(db,db.get(Channel,job.channel_id))).videos().list(part='statistics,snippet',id=task.youtube_video_id).execute()['items'][0]
    except Exception:
        raise HTTPException(502,'YouTube analytics sync failed; check channel connection') from None
    record=db.query(Analytics).filter_by(job_id=job.id).first()
    if not record:
        record=Analytics(id=new_id(),job_id=job.id)
        db.add(record)
    stats=data.get('statistics',{})
    record.views,record.likes,record.comments=int(stats.get('viewCount',0)),int(stats.get('likeCount',0)),int(stats.get('commentCount',0))
    record.last_synced_at=datetime.now(timezone.utc)
    record.published_at=datetime.fromisoformat(data['snippet']['publishedAt'].replace('Z','+00:00'))
    db.commit()
    return {'views':record.views,'likes':record.likes,'comments':record.comments}
