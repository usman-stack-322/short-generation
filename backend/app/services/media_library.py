"""Private reusable media; job copies retain credits and survive library archival."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import or_
from app.core.config import settings
from app.models import MediaCollection, LibraryMedia, MediaUsage, Channel
from app.api.access import _accessible_channel_ids


def collection_access(db, collection_id, member, write=False):
    row=db.get(MediaCollection,collection_id)
    allowed=_accessible_channel_ids(db,member)
    visible=row and row.workspace_id==member.workspace_id and row.member_id==member.id
    if not visible:raise HTTPException(404,'Collection not found')
    if write and (member.role=='VIEWER' or member.role!='OWNER' and row.member_id!=member.id):
        raise HTTPException(403,'Only the collection owner or workspace owner may edit it')
    return row


def library_path(row):
    root=(Path(settings.generated_dir)/'library').resolve()
    path=Path(row.local_path).resolve()
    if root not in path.parents or not path.is_file():raise HTTPException(404,'Media file missing; upload a replacement')
    return path


def collect_saved(db,job,scenes,output_dir):
    """Match exact personality IDs; never use broad tags as identity evidence."""
    from app.services.assets.providers import SafeAsset,validate_local_image
    from app.services.assets.licensed import prepare_photo
    if not job.collection_id and job.content_mode=='hybrid':
        # Also support stage retries of pre-library jobs. Assigned collections
        # are explicitly shared with this channel; private collections excluded.
        chosen=db.query(MediaCollection).join(LibraryMedia).filter(
            MediaCollection.workspace_id==job.workspace_id,MediaCollection.channel_id==job.channel_id,
            LibraryMedia.personality_id==job.personality_id,LibraryMedia.approved.is_(True),
            LibraryMedia.archived.is_(False),LibraryMedia.media_type.in_(['photo','clip'])).order_by(MediaCollection.created_at).first()
        if chosen:job.collection_id=chosen.id
    collection=db.get(MediaCollection,job.collection_id) if job.collection_id else None
    if not collection or collection.workspace_id!=job.workspace_id or collection.channel_id!=job.channel_id:
        return []
    channel=db.get(Channel,job.channel_id)
    # Private, unassigned collections cannot become a worker privilege escalation.
    if not channel or collection.member_id!=channel.member_id:return []
    candidates=db.query(LibraryMedia).filter_by(collection_id=collection.id,approved=True,archived=False,personality_id=job.personality_id).filter(LibraryMedia.media_type.in_(['photo','clip'])).all()
    def last_used(row):
        usage=db.query(MediaUsage).filter_by(media_id=row.id).order_by(MediaUsage.created_at.desc()).first()
        return usage.created_at.isoformat() if usage else ''
    candidates.sort(key=lambda row:(row.media_type!='clip',last_used(row) if job.avoid_recent_media else '',row.id))
    assets=[]
    for scene,row in zip(scenes,candidates):
        try:
            source=library_path(row)
            Path(output_dir).mkdir(parents=True,exist_ok=True)
            path=Path(output_dir)/f'saved_{scene.scene_number}_{uuid4().hex}{source.suffix if row.media_type=="clip" else ".jpg"}'
            if row.media_type=='clip':
                validate_job_media(source,Path(settings.generated_dir));shutil.copyfile(source,path)
            else:
                validate_local_image(source,Path(settings.generated_dir))
                prepare_photo(source.read_bytes(),path,'Archive photo - User supplied')
        except (HTTPException,ValueError,OSError,subprocess.SubprocessError):continue
        credit=f'{row.name} | {row.creator} | {row.source_url or "user-owned original"} | {row.license} | {row.credit} | Proportional resize, archive label and gentle motion'
        assets.append(SafeAsset(path,'Saved collection',row.license,credit[:500],row.source_url,row.creator,None,scene.scene_number,
            {'kind':'archive','label':'Archive photo - User supplied','required_credit':credit,'library_media_id':row.id,
             'content_hash':row.content_hash,'rights_checked':True,'real_photos_only':True,
             'authenticity_note':'User-attested identity and reuse permission; archival photo does not prove this event.'}))
    return assets


def validate_job_media(path,root):
    from app.services.assets.providers import validate_local_image
    path=Path(path).resolve()
    if path.suffix.lower()!='.mp4':return validate_local_image(path,root)
    if root.resolve() not in path.parents or not path.is_file() or path.stat().st_size>80*1024*1024:
        raise ValueError('Invalid saved video file')
    import subprocess
    result=subprocess.run([settings.ffprobe_path,'-v','error','-protocol_whitelist','file,pipe','-show_streams','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=20)
    if not any(s.get('codec_type')=='video' for s in json.loads(result.stdout).get('streams',[])):raise ValueError('Video stream missing')
    return path


def commit_usage(db,job,assets):
    """Called only after successful render; one usage per asset/revision."""
    for asset in assets:
        media_id=json.loads(asset.provenance or '{}').get('library_media_id')
        if media_id and not db.query(MediaUsage).filter_by(media_id=media_id,job_id=job.id,revision=job.media_revision).first():
            db.add(MediaUsage(id=uuid4().hex,media_id=media_id,job_id=job.id,revision=job.media_revision))
