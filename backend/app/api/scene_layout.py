"""Atomic scene layout edits retain narration order and invalidate rendered approval."""
import json
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy.orm import Session
from app.core.security import require_editor
from app.database.session import get_db
from app.models import Scene,Asset,LibraryMedia
from app.youtube.permissions import job_access
from app.services.pipeline import ACTIVE_STATUSES,serialize_job
from app.services.preferences import invalidate_approvals
from app.services.media_library import collection_access,library_path

router=APIRouter()


class SceneSlot(BaseModel):
    model_config=ConfigDict(extra='forbid')
    asset_id:str
    duration:float=Field(gt=.5,le=60)
    focal_x:float=Field(default=.5,ge=0,le=1)
    focal_y:float=Field(default=.5,ge=0,le=1)


class Arrangement(BaseModel):
    revision:int=Field(ge=1)
    scenes:list[SceneSlot]=Field(min_length=1,max_length=20)


@router.put('/api/videos/{job_id}/scene-layout')
def arrange(job_id:str,payload:Arrangement,context=Depends(require_editor),db:Session=Depends(get_db)):
    job=job_access(db,job_id,context[1],True)
    if job.content_revision!=payload.revision:raise HTTPException(409,'Content changed. Refresh before editing scenes')
    if job.status in ACTIVE_STATUSES|{'scheduled','uploaded','uploading','verification_required','research_ready'} or not job.script:
        raise HTTPException(409,'Scene editing is unavailable in this stage')
    scenes=db.query(Scene).filter_by(job_id=job.id).order_by(Scene.scene_number).all()
    assets=db.query(Asset).filter_by(job_id=job.id).all();by_id={a.id:a for a in assets}
    if len(payload.scenes)!=len(scenes) or set(s.asset_id for s in payload.scenes)!=set(by_id) or len(set(s.asset_id for s in payload.scenes))!=len(assets):
        raise HTTPException(422,'Use every current scene photo exactly once')
    expected_duration=round(job.video.duration if job.video else job.duration,2)
    if abs(sum(s.duration for s in payload.scenes)-expected_duration)>.021:
        raise HTTPException(422,f'Scene durations must total {expected_duration} seconds')
    start=0
    for scene,slot in zip(scenes,payload.scenes):
        scene.start_time=start;scene.end_time=start+slot.duration;start=scene.end_time
        asset=by_id[slot.asset_id];asset.scene_number=scene.scene_number
        meta=json.loads(asset.provenance or '{}');meta.update(focal_x=slot.focal_x,focal_y=slot.focal_y)
        asset.provenance=json.dumps(meta)
    trace=json.loads(job.research_trace or '{}');trace['manual_scene_timing']=True;job.research_trace=json.dumps(trace)
    invalidate_approvals(db,job);job.media_revision+=1
    if job.video:job.video.status='outdated'
    job.status='failed';job.current_step='scenes_edited';job.failed_step='rendering'
    job.error_message='Scene layout changed. Regenerate video; narration order is unchanged.'
    db.commit();return serialize_job(job,db)


class SavedPhoto(BaseModel):
    revision:int=Field(ge=1)
    media_id:str


@router.post('/api/videos/{job_id}/assets/{asset_id}/saved')
def saved(job_id:str,asset_id:str,payload:SavedPhoto,context=Depends(require_editor),db:Session=Depends(get_db)):
    from app.api.assets import editable,save
    from app.services.assets.licensed import prepare_photo
    from app.services.assets.providers import SafeAsset
    from app.core.config import settings
    from pathlib import Path
    from uuid import uuid4
    job,record,scene=editable(db,job_id,asset_id,context[1],payload.revision)
    row=db.get(LibraryMedia,payload.media_id)
    if not row:raise HTTPException(404,'Saved photo not found')
    collection=collection_access(db,row.collection_id,context[1])
    if collection.channel_id!=job.channel_id or row.personality_id!=job.personality_id or not row.approved or row.archived or row.media_type!='photo':
        raise HTTPException(422,'Choose an approved matching photo from a collection assigned to this channel')
    path=Path(settings.generated_dir)/'images'/job.id/(uuid4().hex+'.jpg')
    prepare_photo(library_path(row).read_bytes(),path,'Archive photo - User supplied')
    credit=f'{row.name} | {row.creator} | {row.source_url or "user-owned original"} | {row.license} | {row.credit} | Padded, labeled; gentle motion'
    return save(db,job,record,SafeAsset(path,'Saved collection',row.license,credit[:500],row.source_url,row.creator,None,scene.scene_number,
        {'kind':'archive','label':'Archive photo - User supplied','required_credit':credit,'library_media_id':row.id,'content_hash':row.content_hash}))
