"""Resumable official API upload. No caller can bypass persisted approval checks."""
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from app.core.config import settings
from app.core.vault import encrypt
from app.models import Channel, ChannelAuthorization, WorkspaceMember, UploadTask, VideoJob, Asset, MusicTrack
from app.youtube.oauth import credentials_for, youtube
from app.youtube.permissions import approval_satisfied
from app.services.preferences import notify


def upload_guard(db, job, task):
    if not job.video or job.video.media_revision!=job.media_revision or job.video.status=='outdated':
        raise RuntimeError('Upload blocked: rendered media is outdated')
    if job.status != 'approved':
        raise RuntimeError('Upload blocked: job must be approved')
    channel = db.get(Channel, job.channel_id)
    requester = db.get(WorkspaceMember, task.requested_by)
    if not requester or not requester.active or requester.role == 'VIEWER' or requester.workspace_id != job.workspace_id:
        raise RuntimeError('Upload requester is no longer authorized')
    if channel.member_id != requester.id:
        raise RuntimeError('Upload requester is not assigned to this channel')
    if not approval_satisfied(db, job, channel) or task.content_revision != job.content_revision:
        raise RuntimeError('Upload blocked: current content revision needs required approval')
    auth = db.query(ChannelAuthorization).filter_by(channel_id=channel.id).first()
    authorizer = db.get(WorkspaceMember, auth.authorized_member_id) if auth else None
    if not auth or not auth.encrypted_tokens or channel.status=='disconnected' or auth.authorized_member_id != channel.member_id or not authorizer or not authorizer.active or authorizer.role=='VIEWER':
        raise RuntimeError('Channel must be connected by its active assigned member')
    if not job.video or not job.script or not job.script.seo:
        raise RuntimeError('Rendered video and metadata are required')
    if not job.topic or job.topic.verification_status != 'verified':
        raise RuntimeError('Publishing requires a verified topic, not demo or unverified news')
    if not job.voice_generation or 'fallback' in job.voice_generation.provider:
        raise RuntimeError('Publishing requires narration; development silence is not publishable')
    if any('development' in warning.lower() for warning in json.loads(job.warnings or '[]')):
        raise RuntimeError('Publishing requires a real source-grounded script, not development copy')
    for asset in db.query(Asset).filter_by(job_id=job.id):
        metadata=json.loads(asset.provenance or '{}')
        if metadata.get('rights_checked') and metadata.get('required_credit') not in job.script.seo.description:
            raise RuntimeError('Required image credits missing. Regenerate SEO and review again.')
    return channel


def upload(db, job, task):
    if task.youtube_video_id or task.resumable_uri_encrypted:
        raise RuntimeError('Existing upload must be reconciled before any new upload')
    if task.scheduled_at:
        raise RuntimeError('Scheduled uploads are disabled; use YouTube Studio manually')
    task.privacy_status='private'
    channel = upload_guard(db, job, task)
    if not settings.youtube_uploads_enabled:
        raise RuntimeError('YouTube uploads are disabled. Set YOUTUBE_UPLOADS_ENABLED=true after configuration.')
    allowed = [s.strip() for s in settings.youtube_test_channel_ids.split(',') if s.strip()]
    if allowed and channel.youtube_channel_id not in allowed:
        raise RuntimeError('This channel is outside the configured test-channel allowlist')
    root = Path(settings.generated_dir).resolve()
    video = Path(job.video.output_path).resolve()
    if root not in video.parents or video.suffix.lower() != '.mp4' or not video.is_file():
        raise RuntimeError('Rendered MP4 is missing or outside generated media root')
    credentials = credentials_for(db, channel)
    service = youtube(credentials)
    mine = service.channels().list(part='id', mine=True).execute()
    if channel.youtube_channel_id not in [item['id'] for item in mine.get('items', [])]:
        raise RuntimeError('Credential channel mismatch. Reconnect the intended channel.')
    # Recheck after network/refresh work, then atomically lock the approved revision.
    db.refresh(job)
    upload_guard(db, job, task)
    locked = db.query(VideoJob).filter_by(id=job.id, status='approved', content_revision=task.content_revision).update(
        {'status':'uploading','current_step':'uploading'})
    db.commit()
    if locked != 1:
        raise RuntimeError('Approval changed before upload; no video was sent')
    db.refresh(job)
    seo = job.script.seo
    credits = '\n'.join(dict.fromkeys(a.attribution for a in db.query(Asset).filter_by(job_id=job.id) if a.attribution and not json.loads(a.provenance or '{}').get('required_credit') and a.source!='Local text card'))
    if job.music_id:
        music=db.get(MusicTrack,job.music_id)
        if music:
            credits += f'\nMusic: {music.attribution} ? {music.license} ? {music.source}'
    description = seo.description + '\n\n' + ' '.join(json.loads(seo.hashtags)) + '\n\nVisual credits:\n' + credits
    if len(description.encode('utf-8')) > 4800:
        raise RuntimeError('Description and required attribution exceed YouTube limits. Shorten metadata or use fewer assets.')
    body = {'snippet': {'title': seo.title, 'description': description,
                        'tags': json.loads(seo.keywords), 'categoryId': '22'},
            'status': {'privacyStatus': 'private', 'selfDeclaredMadeForKids': task.made_for_kids}}
    request = service.videos().insert(part='snippet,status', body=body,
                media_body=MediaFileUpload(str(video), mimetype='video/mp4', chunksize=1024*1024, resumable=True))
    response, retries = None, 0
    # Persist upload intent before making the first external mutation.
    job.status = job.current_step = 'uploading'
    db.commit()
    while response is None:
        try:
            # Revocation/deactivation takes effect between resumable chunks too.
            db.refresh(channel)
            auth=db.query(ChannelAuthorization).filter_by(channel_id=channel.id).populate_existing().first()
            requester=db.get(WorkspaceMember,task.requested_by);db.refresh(requester)
            if channel.status=='disconnected' or not auth or not auth.encrypted_tokens or not requester.active or channel.member_id!=requester.id:
                raise RuntimeError('Upload connection or account is no longer authorized')
            progress, response = request.next_chunk(num_retries=0)
            if getattr(request, 'resumable_uri', None):
                task.resumable_uri_encrypted = encrypt(request.resumable_uri)
            if progress:
                task.progress = progress.progress()
            db.commit()
        except HttpError as exc:
            if exc.resp.status in {429, 500, 502, 503, 504} and retries < 3:
                retries += 1
                task.retry_count += 1
                db.commit()
                time.sleep(min(2 ** retries, 8))
                continue
            channel.status = 'upload_error'
            raise RuntimeError(f'YouTube rejected upload (HTTP {exc.resp.status}); check account permissions/quota and retry.') from None
    if not response.get('id'):
        raise RuntimeError('YouTube did not return a video ID; reconcile before retrying')
    task.youtube_video_id = response['id']
    task.youtube_url = 'https://www.youtube.com/watch?v=' + response['id']
    task.uploaded_at = datetime.now(timezone.utc)
    task.response = json.dumps({'id': response['id'], 'status': response.get('status', {})})
    task.status, task.progress = 'processing', 1
    task.resumable_uri_encrypted = None
    job.status = job.current_step = 'processing'
    channel.status, channel.connection_error = 'connected', None
    db.commit()
    verify_upload(db,job,task,service)


def verify_upload(db,job,task,service=None):
    """Read-only verification; never change remote visibility or create another upload."""
    try:
        channel=db.get(Channel,job.channel_id)
        service=service or youtube(credentials_for(db,channel))
        items=service.videos().list(part='snippet,status,processingDetails',id=task.youtube_video_id).execute().get('items',[])
        item=items[0] if items else {}
        if item.get('snippet',{}).get('channelId')!=channel.youtube_channel_id or item.get('status',{}).get('privacyStatus')!='private':
            raise ValueError('Private visibility or destination channel could not be verified')
        state=item.get('processingDetails',{}).get('processingStatus')
        upload_state=item.get('status',{}).get('uploadStatus')
        if state in {'failed','terminated'} or upload_state in {'failed','rejected','deleted'}:
            task.status='processing_failed';task.error_message='YouTube processing failed. Keep the export and inspect YouTube Studio.'
        elif state=='succeeded' or upload_state=='processed':
            task.status='uploaded';task.error_message=None
        else:
            task.status='processing';task.error_message=None
    except Exception:
        task.status='visibility_verification_failed'
        task.error_message='Upload has a video ID, but private visibility could not be verified. Check Studio; do not re-upload.'
    job.status=job.current_step=task.status
    db.commit()


def process_upload(db, task):
    job = db.get(VideoJob, task.job_id)
    try:
        # Claim once. Multiple scheduler polls cannot start the same task twice.
        claimed = db.query(UploadTask).filter(UploadTask.id == task.id, UploadTask.status=='pending',UploadTask.scheduled_at.is_(None)).update({'status': 'uploading'})
        db.commit()
        if not claimed:
            return
        db.refresh(task)
        db.refresh(job)
        if job.status == 'scheduled':
            job.status = 'approved'
            db.commit()
        upload(db, job, task)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('Upload task %s failed', task.id)
        db.rollback()
        db.refresh(job)
        db.refresh(task)
        # An ambiguous network interruption may have created a remote video. Never retry it blindly.
        task.status = 'upload_uncertain' if task.resumable_uri_encrypted or job.status=='uploading' else 'upload_failed'
        task.error_message = str(exc)[:1500] if isinstance(exc, RuntimeError) else 'Upload interrupted; check YouTube Studio before retrying.'
        job.status = job.current_step = 'upload_failed'
        job.error_message = task.error_message
        notify(db, job.workspace_id, job.channel_id, 'Upload failed', task.error_message)
        db.commit()
