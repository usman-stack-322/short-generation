"""Authorized scene photo edits use the existing content/media revision system."""
import json
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import require_editor
from app.database.session import get_db
from app.models import Asset, Scene, Personality
from app.youtube.permissions import job_access
from app.services.preferences import invalidate_approvals
from app.services.pipeline import serialize_job, ACTIVE_STATUSES
from app.services.assets.licensed import collect_scene_assets, neutral_card, prepare_photo
from app.services.assets.credits import sync_credits
from app.core.network import reference_urls

router=APIRouter()


class EditPhoto(BaseModel):
    revision:int=Field(ge=1)


def editable(db,job_id,asset_id,member,revision):
    job=job_access(db,job_id,member,True)
    if revision!=job.content_revision:raise HTTPException(409,'Content changed. Refresh before changing photos.')
    if job.status in ACTIVE_STATUSES|{'scheduled','uploading','uploaded','verification_required','research_ready'} or not job.script:
        raise HTTPException(409,'Stop generation/scheduling before editing scene photos.')
    asset=db.get(Asset,asset_id)
    if not asset or asset.job_id!=job.id:raise HTTPException(404,'Scene photo not found')
    scene=db.query(Scene).filter_by(job_id=job.id,scene_number=asset.scene_number).first()
    if not scene:raise HTTPException(409,'Scene plan unavailable. Regenerate assets first.')
    return job,asset,scene


def save(db,job,record,asset):
    for field in ('source','license','attribution','url','creator','download_url'):
        setattr(record,field,getattr(asset,field))
    record.local_path=str(asset.local_path);record.provenance=json.dumps(asset.provenance)
    invalidate_approvals(db,job);job.media_revision+=1
    if job.video:job.video.status='outdated'
    job.status='failed';job.current_step='assets_edited';job.failed_step='rendering'
    job.error_message='Scene images changed. Regenerate video to preview and approve the updated version.'
    try:sync_credits(db,job)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    db.commit()
    return serialize_job(job,db)


@router.post('/api/videos/{job_id}/assets/{asset_id}/remove')
def remove_photo(job_id:str,asset_id:str,payload:EditPhoto,context=Depends(require_editor),db:Session=Depends(get_db)):
    job,record,scene=editable(db,job_id,asset_id,context[1],payload.revision)
    return save(db,job,record,neutral_card(scene,Path(settings.generated_dir)/'images'/job.id,'Photograph removed by reviewer'))


@router.post('/api/videos/{job_id}/assets/{asset_id}/replace')
def replace_photo(job_id:str,asset_id:str,payload:EditPhoto,context=Depends(require_editor),db:Session=Depends(get_db)):
    job,record,scene=editable(db,job_id,asset_id,context[1],payload.revision)
    existing=db.query(Asset).filter_by(job_id=job.id).all()
    exclude=[a.download_url for a in existing if a.download_url]
    hashes=[json.loads(a.provenance or '{}').get('content_hash') for a in existing]
    personality=db.get(Personality,job.personality_id)
    replacement=collect_scene_assets([scene],job.topic_title,personality.name,job.script.full_script,
        Path(settings.generated_dir)/'images'/job.id,settings.asset_provider,language=job.language_code,exclude_urls=exclude,exclude_hashes=hashes,subject_category=personality.category)[0]
    if replacement.provenance.get('kind')=='missing':
        raise HTTPException(422,'No different eligible photograph found. Current photo preserved. Upload a licensed photograph or remove it.')
    return save(db,job,record,replacement)


@router.post('/api/videos/{job_id}/assets/{asset_id}/upload')
async def upload_photo(job_id:str,asset_id:str,revision:int=Form(...),file:UploadFile=File(...),
    creator:str=Form(...,min_length=1,max_length=200),source_url:str=Form('',max_length=1000),
    license:str=Form(...),rights_confirmed:bool=Form(False),real_photo_confirmed:bool=Form(False),
    capture_date:str=Form('',max_length=100),source_title:str=Form('',max_length=300),
    context=Depends(require_editor),db:Session=Depends(get_db)):
    job,record,scene=editable(db,job_id,asset_id,context[1],revision)
    if not rights_confirmed or not real_photo_confirmed:
        raise HTTPException(422,'Confirm reuse rights and that this is an authentic contextual photograph, not synthetic artwork.')
    licenses={'CC0':'https://creativecommons.org/publicdomain/zero/1.0/',
        **{f'CC BY {version}.0':f'https://creativecommons.org/licenses/by/{version}.0/' for version in range(1,5)},'Own photograph':''}
    if license not in licenses:raise HTTPException(422,'Use CC0, CC BY 1.0–4.0 or your own photograph; share-alike is not supported.')
    try:
        if capture_date:
            from datetime import date
            date.fromisoformat(capture_date)
        if source_url:reference_urls([source_url])
        if license!='Own photograph' and not source_url:raise ValueError('A public source page is required for licensed uploads.')
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    if file.content_type not in {'image/jpeg','image/png','image/webp'}:
        raise HTTPException(422,'Upload a JPEG, PNG or WebP photograph.')
    body=await file.read(15*1024*1024+1)
    if len(body)>15*1024*1024:raise HTTPException(413,'Photograph exceeds 15 MB')
    path=Path(settings.generated_dir)/'images'/job.id/f'scene_{scene.scene_number}_{uuid4().hex}.jpg'
    label='Illustrative archive'+(' - '+capture_date[:4] if capture_date else '')
    try:prepare_photo(body,path,label)
    except Exception:raise HTTPException(422,'Invalid or unsafe photo. Use JPEG/PNG/WebP, at least 400px per side and at most 40 megapixels.') from None
    from app.services.assets.providers import SafeAsset
    credit=f'{source_title or "Photo"} | Photo by {creator}: {source_url or "user-owned original"} | {license} {licenses[license]} | '+(f'Photo date: {capture_date}; illustrative, not the historical award event. | ' if capture_date else '')+'Resized proportionally, padded and labeled; gentle pan/zoom'
    asset=SafeAsset(path,'User photograph',license,credit[:500],source_url or None,creator,None,scene.scene_number,
        {'kind':'context','label':label,'license_url':licenses[license],'date':capture_date or None,'title':source_title or None,
         'required_credit':credit,'modifications':'Proportional resize, padding, label, gentle motion',
         'rights_checked':True,'real_photos_only':True,'authenticity_note':'User attested rights and authentic photography; identity/event association requires human review.'})
    return save(db,job,record,asset)
