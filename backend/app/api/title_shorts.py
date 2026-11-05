"""Authenticated title-short drafts; script review is an explicit render boundary."""
import json,hashlib,uuid
from sqlalchemy.exc import IntegrityError
from pathlib import Path
from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException,Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import current_context,require_editor,new_id,bearer
from app.database.session import get_db
from app.models import TitleShortDraft
from app.services.title_shorts import ACTIVE,TitleInput,EditInput,ActionInput,SceneInput,SourcesInput,work,Plan,preflight

router=APIRouter(prefix='/api/title-shorts',tags=['Title to AI Short'])


def access(db,id,membership):
    row=db.get(TitleShortDraft,id)
    if not row or row.workspace_id!=membership.workspace_id or row.creator_id!=membership.user_id:
        raise HTTPException(404,'Title short not found')
    return row


def public(row):
    data=json.loads(row.data);plan=data.get('plan');assets=data.get('assets',[])
    base='/api/title-shorts/'+row.id+'/media/'
    scenes=[]
    for i,s in enumerate((plan or {}).get('scenes',[])):
        asset=assets[i] if i<len(assets) else None
        scenes.append({**s,'asset':{k:v for k,v in asset.items() if k!='path'} if asset else None,
            'preview_url':base+'image?scene='+str(i+1)+'&revision='+str(row.revision) if asset else None})
    from app.services.title_scope import accepted
    video=data.get('video')
    return {'id':row.id,'title':row.title,'duration':row.duration,'language':row.language,'style':row.style,
        'status':row.status,'revision':row.revision,'error_message':row.error_message,'failed_step':data.get('failed_step'),
        'source_urls':data.get('source_urls',[]),'narrator':data.get('narrator','automatic'),'research_diagnostics':data.get('research_diagnostics',[]),
        'research_state':data.get('research_state'),'research_failure_code':data.get('research_failure_code'),'research_candidates':data.get('research_candidates',[]),'primary_media':data.get('primary_media',[]),'evidence_review':data.get('evidence_review'),'lead':data.get('lead'),
        'scope':data.get('scope'),'scope_accepted':accepted(data),'analysis':data.get('analysis'),'sources':data.get('sources',[]),'claims':(plan or {}).get('claims',[]),
        'scene_timing':data.get('scene_timing','estimated until final narration'),
        'scenes':scenes,'script':' '.join(s['narration'] for s in scenes),'voice':data.get('voice'),
        'video_url':base+'video?revision='+str(video['revision']) if video else None,
        'credits_url':base+'credits?revision='+str(video['revision']) if video else None,
        'sources_url':base+'sources?revision='+str(video['revision']) if video else None,
        'output_duration':video.get('duration') if video else None,'render_history':[{'revision':v['revision'],'duration':v['duration'],'video_url':base+'video?revision='+str(v['revision'])} for v in data.get('renders',[])],
        'media_mode':data.get('media_mode','online'),'collection_id':data.get('collection_id'),
        'online_fallback':data.get('online_fallback',False),'channel_id':data.get('channel_id'),
        'video_job_id':data.get('video_job_id'),'scene_locks':data.get('scene_locks',[]),
        'uploads_enabled':settings.youtube_uploads_enabled,'created_at':row.created_at.isoformat()}


def claim(db,row,revision,status):
    changed=db.query(TitleShortDraft).filter(TitleShortDraft.id==row.id,TitleShortDraft.revision==revision,~TitleShortDraft.status.in_(ACTIVE)).update(
        {'revision':revision+1,'status':status,'error_message':None},synchronize_session=False)
    if changed!=1:db.rollback();raise HTTPException(409,'Draft changed or is already processing. Refresh before retrying.')
    db.commit();db.refresh(row)


@router.get('')
def listing(context=Depends(current_context),db:Session=Depends(get_db)):
    q=db.query(TitleShortDraft).filter_by(workspace_id=context[1].workspace_id)
    q=q.filter_by(creator_id=context[0].id)
    return [public(row) for row in q.order_by(TitleShortDraft.created_at.desc()).limit(50)]


@router.post('',status_code=201)
def create(payload:TitleInput,background:BackgroundTasks,context=Depends(require_editor),db:Session=Depends(get_db)):
    if payload.collection_id:
        from app.services.media_library import collection_access
        collection_access(db,payload.collection_id,context[1])
    if payload.media_mode in {'local','mixed'} and not payload.collection_id:
        raise HTTPException(422,'Select a personal collection for local media')
    if payload.channel_id:
        from app.models import Channel
        from app.youtube.permissions import channel_access
        channel_access(db.get(Channel,payload.channel_id),context[1],True)
    fingerprint=hashlib.sha256(json.dumps(payload.model_dump(exclude={'request_id'}),sort_keys=True).encode()).hexdigest()
    key=str(uuid.uuid5(uuid.NAMESPACE_URL,context[1].workspace_id+':'+context[0].id+':'+payload.request_id)) if payload.request_id else new_id()
    def existing():
        found=db.get(TitleShortDraft,key)
        if found and json.loads(found.data).get('request_fingerprint')!=fingerprint:raise HTTPException(409,'Request ID already used with different inputs. Start a new short.')
        return public(found) if found else None
    previous=existing()
    if previous:return previous
    # Missing configuration is actionable before allocating a worker.
    if not settings.gemini_api_key.strip():raise HTTPException(503,'Configure GEMINI_API_KEY and GEMINI_MODEL on the server. Title analysis/researched scripts require the AI service; development fallback is disabled.')
    check=preflight(payload.language,payload.narrator)
    if not check['available']:raise HTTPException(422,check['message'])
    row=TitleShortDraft(id=key,workspace_id=context[1].workspace_id,creator_id=context[0].id,**payload.model_dump(include={'title','duration','language','style'}),status='analyzing',data=json.dumps({**payload.model_dump(include={'source_urls','narrator','media_mode','collection_id','online_fallback','channel_id'}),'request_fingerprint':fingerprint}))
    db.add(row)
    try:db.commit()
    except IntegrityError:
        db.rollback()
        previous=existing()
        if previous:return previous
        raise
    db.refresh(row);background.add_task(work,row.id,'prepare')
    return public(row)


@router.get('/capabilities')
def capabilities(context=Depends(current_context)):
    return {'languages':{lang:preflight(lang) for lang in ['English','Urdu','Roman Urdu']},'local_english':preflight('English','local')}


@router.post('/{id}/sources',status_code=202)
def set_sources(id:str,payload:SourcesInput,background:BackgroundTasks,context=Depends(require_editor),db:Session=Depends(get_db)):
    row=access(db,id,context[1]);data=json.loads(row.data)
    check=preflight(row.language,data.get('narrator','automatic'))
    if not check['available']:raise HTTPException(422,check['message'])
    claim(db,row,payload.revision,'analyzing')
    data['source_urls']=payload.source_urls
    row.data=json.dumps(data);db.commit();background.add_task(work,id,'research' if data.get('plan') else 'prepare');return public(row)


@router.get('/{id}')
def get(id:str,context=Depends(current_context),db:Session=Depends(get_db)):
    return public(access(db,id,context[1]))


@router.put('/{id}/script')
def edit(id:str,payload:EditInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    row=access(db,id,context[1]);data=json.loads(row.data)
    if not data.get('plan'):raise HTTPException(409,'Wait for researched script generation.')
    if len(payload.narrations)!=len(data['plan']['scenes']) or any(not s.strip() or len(s)>1500 for s in payload.narrations):
        raise HTTPException(422,'Supply one non-empty narration per existing scene, at most 1500 characters each.')
    from app.services.title_shorts import check_plan
    import copy
    data.setdefault('script_history',[]).append({'revision':row.revision,'plan':copy.deepcopy(data['plan']),'scope':copy.deepcopy(data.get('scope'))})
    for i,text in enumerate(payload.narrations):
        if text!=data['plan']['scenes'][i]['narration']:data['assets'][i]=None
        data['plan']['scenes'][i]['narration']=text
    # Local length/language/evidence checks here; final source audit is mandatory on render.
    try:check_plan(row,data['plan'],data['sources'],verify=False)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None
    claim(db,row,payload.revision,'script_review')
    data.pop('video',None);data['review_required']=True
    row.data=json.dumps(data,ensure_ascii=False);db.commit();return public(row)


@router.post('/{id}/scope/accept')
def accept_scope(id:str,payload:ActionInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    from app.services.title_scope import fingerprint
    from app.services.title_shorts import check_plan
    from datetime import datetime,timezone
    row=access(db,id,context[1]);data=json.loads(row.data)
    if row.status!='script_review' or data.get('research_state')!='verified' or not data.get('scope',{}).get('required') or not data.get('plan'):raise HTTPException(409,'A verified revised scope and script must be ready for review.')
    try:check_plan(row,data['plan'],data['sources'],verify=False)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    claim(db,row,payload.revision,'script_review')
    data['scope']['accepted_fingerprint']=fingerprint(data)
    data['scope']['accepted_by']=context[0].id
    data['scope']['accepted_at']=datetime.now(timezone.utc).isoformat()
    row.data=json.dumps(data,ensure_ascii=False);db.commit();return public(row)


@router.post('/{id}/render',status_code=202)
def render(id:str,payload:ActionInput,background:BackgroundTasks,context=Depends(require_editor),db:Session=Depends(get_db)):
    row=access(db,id,context[1]);data=json.loads(row.data)
    from app.services.title_scope import accepted
    if not accepted(data):raise HTTPException(409,'Accept the current revised scope and script before rendering.')
    if data.get('research_state') in {'failed','in_progress'}:raise HTTPException(409,'Latest research is not verified. Retry research before rendering.')
    if not data.get('plan') or not data.get('sources'):raise HTTPException(409,'A researched script must be reviewed before rendering.')
    check=preflight(row.language,data.get('narrator','automatic'))
    if not check['available']:raise HTTPException(422,check['message'])
    claim(db,row,payload.revision,'validating')
    data.pop('video',None);data.pop('voice',None);data.pop('scene_timing',None)
    row.data=json.dumps(data,ensure_ascii=False);db.commit()
    background.add_task(work,id,'render');return public(row)


@router.post('/{id}/retry',status_code=202)
def retry(id:str,payload:ActionInput,background:BackgroundTasks,refresh_sources:bool=True,context=Depends(require_editor),db:Session=Depends(get_db)):
    row=access(db,id,context[1]);data=json.loads(row.data)
    operation='audit' if not refresh_sources and data.get('failed_step') in {'research_verification','script'} and data.get('sources') and data.get('analysis') else 'research' if data.get('plan') else 'prepare'
    claim(db,row,payload.revision,'research_verification' if operation=='audit' else 'analyzing');background.add_task(work,id,operation);return public(row)


@router.post('/{id}/scenes/{number}/regenerate',status_code=202)
def regenerate(id:str,number:int,payload:SceneInput,background:BackgroundTasks,context=Depends(require_editor),db:Session=Depends(get_db)):
    row=access(db,id,context[1]);data=json.loads(row.data)
    if not data.get('plan') or not 1<=number<=len(data['plan']['scenes']):raise HTTPException(404,'Scene not found')
    if number in data.get('scene_locks',[]):raise HTTPException(409,'Unlock this scene before regenerating')
    claim(db,row,payload.revision,'visuals');background.add_task(work,id,'scene',number,payload.instruction);return public(row)



@router.post('/{id}/scenes/{number}/rewrite',status_code=202)
def rewrite(id:str,number:int,payload:SceneInput,background:BackgroundTasks,context=Depends(require_editor),db:Session=Depends(get_db)):
    row=access(db,id,context[1]);data=json.loads(row.data)
    if not data.get('plan') or not 1<=number<=len(data['plan']['scenes']):raise HTTPException(404,'Scene not found')
    if number in data.get('scene_locks',[]):raise HTTPException(409,'Unlock this scene before regenerating')
    claim(db,row,payload.revision,'script');background.add_task(work,id,'rewrite',number,payload.instruction);return public(row)


class LocalSceneInput(ActionInput):
    media_id:str|None=None
    exclude:bool=False
    locked:bool=False
    swap_with:int|None=None


@router.put('/{id}/scenes/{number}/local-image')
def local_scene(id:str,number:int,payload:LocalSceneInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    from app.api.library import asset_access
    from app.services.title_library import copy_local
    row=access(db,id,context[1]);data=json.loads(row.data)
    assets=data.get('assets',[])
    if not 1<=number<=len(assets):raise HTTPException(404,'Scene not found')
    locks=set(data.get('scene_locks',[]))
    if number in locks and (payload.media_id or payload.exclude or payload.swap_with):raise HTTPException(409,'Unlock scene first')
    if payload.swap_with:
        other=payload.swap_with
        if not 1<=other<=len(assets) or other in locks:raise HTTPException(422,'Select an unlocked scene')
        assets[number-1],assets[other-1]=assets[other-1],assets[number-1]
    elif payload.media_id:
        media=asset_access(db,payload.media_id,context[1])
        if not media.approved or media.archived or media.media_type!='photo':raise HTTPException(422,'Select an approved photograph with confirmed tags and rights')
        assets[number-1]=copy_local(row,media)
    elif payload.exclude:
        old=assets[number-1]
        if old:data.setdefault('excluded_hashes',[]).append(old['hash'])
        assets[number-1]=None
    if payload.locked:locks.add(number)
    else:locks.discard(number)
    claim(db,row,payload.revision,'script_review')
    data['scene_locks']=sorted(locks);data['assets']=assets;data.pop('video',None)
    row.data=json.dumps(data);db.commit();return public(row)


class FinalizeInput(ActionInput):
    channel_id:str
    title:str=__import__('pydantic').Field(min_length=1,max_length=100)
    description:str=__import__('pydantic').Field(min_length=1,max_length=4000)


@router.post('/{id}/finalize')
def finalize(id:str,payload:FinalizeInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    from app.services.title_export import finalize_draft
    row=access(db,id,context[1])
    return finalize_draft(db,row,payload,context[1])


def media_context(request:Request,credentials=Depends(bearer),db:Session=Depends(get_db)):
    if credentials is None and request.cookies.get('media_session'):
        credentials=HTTPAuthorizationCredentials(scheme='Bearer',credentials=request.cookies['media_session'])
    return current_context(credentials,db)


@router.get('/{id}/media/{kind}')
def media(id:str,kind:str,revision:int,scene:int=1,download:bool=False,context=Depends(media_context),db:Session=Depends(get_db)):
    row=access(db,id,context[1]);data=json.loads(row.data)
    if kind in {'video','credits','sources'}:
        records=[*data.get('renders',[]),data.get('video') or {}];record=next((r for r in records if r.get('revision')==revision),None)
        if not record:raise HTTPException(404,'Rendered revision not found')
        path=Path(record['path'])
        if kind=='credits':path=path.parent/'credits.txt'
        if kind=='sources':path=path.parent/'research-sources.json'
    elif kind=='image' and revision==row.revision and 1<=scene<=len(data.get('assets',[])) and data['assets'][scene-1]:
        path=Path(data['assets'][scene-1]['path'])
    else:raise HTTPException(404,'Media not found or stale revision')
    root=Path(settings.generated_dir).resolve()/'title-shorts'/id
    if root not in path.resolve().parents or not path.is_file():raise HTTPException(404,'Media not found')
    return FileResponse(path,filename=('title-short-'+id+path.suffix) if download else None,
        headers={'Cache-Control':'private, no-store'},content_disposition_type='attachment' if download else 'inline')
