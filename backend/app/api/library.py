"""Authenticated reusable media CRUD. Archival never removes referenced job copies."""
import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Form,Request
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import current_context,require_editor,require_owner,bearer
from app.database.session import get_db
from app.models import MediaCollection,LibraryMedia,MediaUsage,Channel,Personality
from app.api.access import _accessible_channel_ids,personality_visible
from app.services.media_library import collection_access,library_path

router=APIRouter(prefix='/api/library',tags=['Media library'])


class CollectionInput(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    name:str=Field(min_length=2,max_length=160)
    channel_id:str|None=None


class MediaEdit(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    name:str=Field(min_length=1,max_length=160)
    tags:list[str]=Field(default_factory=list,max_length=20)
    credit:str=Field(default='',max_length=2000)
    approved:bool=False
    description:str=Field(default='',max_length=2000)


def channel_check(db,channel_id,member):
    if not channel_id:return
    row=db.get(Channel,channel_id);ids=_accessible_channel_ids(db,member)
    if not row or row.workspace_id!=member.workspace_id or ids is not None and row.id not in ids:
        raise HTTPException(404,'Assigned channel not found')


def asset_access(db,media_id,member,write=False):
    row=db.get(LibraryMedia,media_id)
    if not row:raise HTTPException(404,'Media not found')
    collection_access(db,row.collection_id,member,write)
    return row


def serialize(db,row):
    return {'id':row.id,'collection_id':row.collection_id,'personality_id':row.personality_id,'name':row.name,
        'media_type':row.media_type,'tags':json.loads(row.tags),'description':row.description,'width':row.width,'height':row.height,'source_url':row.source_url,'creator':row.creator,
        'license':row.license,'credit':row.credit,'approved':row.approved,'archived':row.archived,
        'usage_count':db.query(MediaUsage).filter_by(media_id=row.id).count(),
        'preview_url':f'/api/library/media/{row.id}/preview','available':Path(row.local_path).is_file()}


@router.get('/collections')
def collections(context=Depends(current_context),db:Session=Depends(get_db)):
    rows=db.query(MediaCollection).filter_by(workspace_id=context[1].workspace_id).all();result=[]
    for row in rows:
        try:collection_access(db,row.id,context[1])
        except HTTPException:continue
        result.append({'id':row.id,'name':row.name,'channel_id':row.channel_id,'member_id':row.member_id})
    return result


@router.post('/collections',status_code=201)
def create(payload:CollectionInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    channel_check(db,payload.channel_id,context[1])
    row=MediaCollection(id=uuid4().hex,workspace_id=context[1].workspace_id,member_id=context[1].id,**payload.model_dump())
    db.add(row);db.commit()
    return {'id':row.id,'name':row.name,'channel_id':row.channel_id,'member_id':row.member_id}


@router.patch('/collections/{collection_id}')
def edit_collection(collection_id:str,payload:CollectionInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    row=collection_access(db,collection_id,context[1],True);channel_check(db,payload.channel_id,context[1])
    row.name=payload.name;row.channel_id=payload.channel_id;db.commit()
    return {'id':row.id,'name':row.name,'channel_id':row.channel_id,'member_id':row.member_id}


@router.get('/collections/{collection_id}/media')
def media_list(collection_id:str,q:str='',media_type:str='',approved:bool|None=None,context=Depends(current_context),db:Session=Depends(get_db)):
    collection_access(db,collection_id,context[1])
    rows=db.query(LibraryMedia).filter_by(collection_id=collection_id,archived=False).all()
    return [serialize(db,r) for r in rows if (not q or q.casefold() in (r.name+' '+r.tags).casefold()) and (not media_type or r.media_type==media_type) and (approved is None or r.approved==approved)]


@router.post('/collections/{collection_id}/media',status_code=201)
async def upload(collection_id:str,file:UploadFile=File(...),name:str=Form(...,min_length=1,max_length=160),
    media_type:str=Form('photo'),personality_id:str|None=Form(None),creator:str=Form(...,min_length=1,max_length=200),
    source_url:str=Form('',max_length=1000),license:str=Form('Own work'),credit:str=Form('',max_length=2000),
    rights_confirmed:bool=Form(False),identity_confirmed:bool=Form(False),
    context=Depends(require_editor),db:Session=Depends(get_db)):
    collection_access(db,collection_id,context[1],True)
    if not rights_confirmed:raise HTTPException(422,'Confirm permission to reuse and modify this media')
    if license not in {'Own work','CC0','CC BY 4.0','Written permission'}:raise HTTPException(422,'Unsupported reuse permission')
    if license not in {'Own work','Written permission'} and not source_url:raise HTTPException(422,'Provide the licensed source page')
    if source_url:
        from app.core.network import reference_urls
        try:reference_urls([source_url])
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
    if personality_id:
        p=db.get(Personality,personality_id)
        if not personality_visible(p,context[1],_accessible_channel_ids(db,context[1])):raise HTTPException(404,'Personality not found')
        if not identity_confirmed:raise HTTPException(422,'Confirm the media depicts the selected personality; no synthetic impersonations')
    types={'photo':{'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp'},'brand':{'image/png':'.png','image/jpeg':'.jpg'},
        'clip':{'video/mp4':'.mp4'},'audio':{'audio/wav':'.wav','audio/x-wav':'.wav','audio/mpeg':'.mp3','audio/mp4':'.m4a','audio/ogg':'.ogg'}}
    suffix=types.get(media_type,{}).get(file.content_type)
    if not suffix:raise HTTPException(422,'Unsupported media type. Use JPEG/PNG/WebP photos, MP4 clips, or WAV/MP3/M4A/OGG audio.')
    limit=(15 if media_type in {'photo','brand'} else 80)*1024*1024
    body=await file.read(limit+1)
    if not body or len(body)>limit:raise HTTPException(413,'Empty file or media size limit exceeded')
    digest=hashlib.sha256(body).hexdigest()
    previous=db.query(LibraryMedia).join(MediaCollection).filter(MediaCollection.member_id==context[1].id,LibraryMedia.content_hash==digest,LibraryMedia.archived.is_(False)).first()
    if previous:
        if previous.archived:raise HTTPException(409,'This file is archived in the collection; use a different file or contact its owner')
        return {**serialize(db,previous),'reused':True}
    path=Path(settings.generated_dir)/'library'/collection_id/(uuid4().hex+suffix);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(body)
    dimensions={}
    original=None
    try:
        if media_type in {'photo','brand'}:
            from app.services.assets.providers import validate_local_image
            validate_local_image(path,Path(settings.generated_dir))
            from PIL import Image,ImageOps
            with Image.open(path) as image:
                if image.format not in {'JPEG','PNG','WEBP'}:raise ValueError('Unsupported actual image format')
                if image.width*image.height>40_000_000 or min(image.size)<400:raise ValueError('Image must be at least 400px per side and under 40 megapixels')
                image.load()
                original=path.with_name(path.stem+'-original'+path.suffix)
                original.write_bytes(body)
                normalized=ImageOps.exif_transpose(image).convert('RGB')
                dimensions={'width':normalized.width,'height':normalized.height}
                normalized.save(path,format='PNG' if suffix=='.png' else 'WEBP' if suffix=='.webp' else 'JPEG')
        else:
            result=subprocess.run([settings.ffprobe_path,'-v','error','-protocol_whitelist','file,pipe','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=20)
            meta=json.loads(result.stdout);kinds={s['codec_type'] for s in meta['streams']}
            if media_type=='audio' and kinds!={'audio'} or media_type=='clip' and 'video' not in kinds:raise ValueError('Media streams do not match selected type')
            if not 0<float(meta['format']['duration'])<=600:raise ValueError('Use media no longer than ten minutes')
    except Exception:
        path.unlink(missing_ok=True)
        if original:original.unlink(missing_ok=True)
        raise HTTPException(422,'Corrupt, unsafe, oversized or unsupported media; check dimensions and duration') from None
    row=LibraryMedia(id=uuid4().hex,collection_id=collection_id,personality_id=personality_id or None,name=name,media_type=media_type,
        source_url=source_url or None,creator=creator,license=license,credit=credit,local_path=str(path),content_hash=digest,
        original_path=str(original) if original else None,**dimensions)
    db.add(row)
    try:db.commit()
    except IntegrityError:
        db.rollback();path.unlink(missing_ok=True)
        row=db.query(LibraryMedia).filter_by(collection_id=collection_id,content_hash=digest).one()
    return serialize(db,row)


@router.patch('/media/{media_id}')
def update(media_id:str,payload:MediaEdit,context=Depends(require_editor),db:Session=Depends(get_db)):
    row=asset_access(db,media_id,context[1],True)
    if row.archived:raise HTTPException(409,'Archived media cannot be approved')
    library_path(row)
    for key,value in payload.model_dump().items():setattr(row,key,json.dumps(value) if key=='tags' else value)
    db.commit();return serialize(db,row)


class FolderInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    relative_path:str=Field(default='',max_length=1000)
    rights_confirmed:bool=False


@router.post('/collections/{collection_id}/import-folder')
async def import_folder(collection_id:str,payload:FolderInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    """One-time local import. Hosted clients use browser selection and uploads."""
    import io,mimetypes,os
    from starlette.datastructures import Headers
    collection_access(db,collection_id,context[1],True)
    configured=json.loads(settings.local_media_roots).get(context[1].id)
    if not configured:raise HTTPException(403,'No local folder permitted for this member. Use browser Import Folder instead.')
    if not payload.rights_confirmed:raise HTTPException(422,'Confirm reuse rights for imported files')
    if not Path(configured).is_absolute():raise HTTPException(503,'Operator-permitted folder must be absolute')
    root=Path(configured).resolve();relative=Path(payload.relative_path)
    if relative.is_absolute() or relative.drive or '..' in relative.parts:
        raise HTTPException(422,'Use a relative subfolder within your permitted root')
    target=(root/relative).resolve()
    if target!=root and root not in target.parents:raise HTTPException(403,'Folder outside permitted root')
    if not target.is_dir():raise HTTPException(404,'Folder not found')
    result=[];visited=0
    for folder,dirs,files in os.walk(target,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(folder)/d).is_symlink() and not (Path(folder)/d).is_junction()]
        for name in files:
            visited+=1
            if visited>500:raise HTTPException(422,'Import limited to 500 directory entries; choose a smaller folder')
            path=Path(folder)/name
            if path.suffix.lower() not in {'.jpg','.jpeg','.png','.webp'}:continue
            resolved=path.resolve()
            if path.is_symlink() or root not in resolved.parents or not resolved.is_file():continue
            if resolved.stat().st_size>15*1024*1024:
                result.append({'name':name,'error':'File exceeds 15 MB'});continue
            file=UploadFile(file=io.BytesIO(resolved.read_bytes()),filename=name,headers=Headers({'content-type':mimetypes.guess_type(name)[0] or ''}))
            try:
                row=await upload(collection_id,file=file,name=path.stem[:160],media_type='photo',personality_id=None,
                    creator=context[0].name,source_url='',license='Own work',credit='',rights_confirmed=True,
                    identity_confirmed=False,context=context,db=db)
                result.append({'name':name,'media':row})
            except HTTPException as exc:result.append({'name':name,'error':exc.detail})
    return {'files':result,'synchronization':False}


@router.delete('/media/{media_id}')
def remove(media_id:str,context=Depends(require_editor),db:Session=Depends(get_db)):
    row=asset_access(db,media_id,context[1],True);row.archived=True;row.approved=False;db.commit()
    return {'archived':True,'detail':'Removed from future selection. Existing rendered revisions and source file preserved.'}


@router.post('/media/{media_id}/workspace-music')
def workspace_music(media_id:str,context=Depends(require_owner),db:Session=Depends(get_db)):
    """Explicit owner action publishes a copy into the existing workspace music pool."""
    import shutil
    from app.models import MusicTrack
    row=asset_access(db,media_id,context[1])
    if row.media_type!='audio' or row.archived or not row.approved:raise HTTPException(422,'Approve an available audio file first')
    source=library_path(row)
    from app.video.renderer import validate_music
    validate_music(source)
    key='library-'+row.id
    track=db.get(MusicTrack,key)
    if not track:
        target=Path(settings.generated_dir)/'music'/(key+source.suffix);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        track=MusicTrack(id=key,workspace_id=context[1].workspace_id,name=row.name,local_path=str(target),
            source=row.source_url or 'User-owned original',license=row.license,attribution=f'{row.creator} | {row.credit}'[:500]);db.add(track);db.commit()
    return {'id':track.id,'detail':'Copied to workspace music. Select it under Settings / Background music; narration is unchanged.'}


@router.get('/media/{media_id}/preview')
def preview(media_id:str,request:Request,credentials=Depends(bearer),db:Session=Depends(get_db)):
    from fastapi.security import HTTPAuthorizationCredentials
    if credentials is None and request.cookies.get('media_session'):
        credentials=HTTPAuthorizationCredentials(scheme='Bearer',credentials=request.cookies['media_session'])
    context=current_context(credentials,db)
    row=asset_access(db,media_id,context[1]);return FileResponse(library_path(row),headers={'Cache-Control':'private, no-store'})
