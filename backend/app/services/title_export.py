"""Rendered title drafts become ordinary jobs; source drafts and exports survive."""
import json,hashlib,shutil,uuid
from pathlib import Path
from fastapi import HTTPException
from app.core.config import settings
from app.core.security import new_id
from app.models import Channel,Personality,Topic,VideoJob,Script,SEOData,Video,VoiceGeneration,Scene,Asset
from app.youtube.permissions import channel_access


def finalize_draft(db,row,payload,member):
    data=json.loads(row.data);render=data.get('video')
    channel=db.get(Channel,payload.channel_id);channel_access(channel,member,True)
    if payload.revision!=row.revision or row.status!='ready' or not render:
        raise HTTPException(409,'Review the current successfully rendered draft first')
    if data.get('research_state')!='verified':raise HTTPException(409,'Verified research required')
    key=str(uuid.uuid5(uuid.NAMESPACE_URL,'title-export:'+row.id+':'+str(row.revision)))
    existing=db.get(VideoJob,key)
    if existing:return {'job_id':existing.id}
    source=Path(render['path']).resolve();root=Path(settings.generated_dir).resolve()
    if root not in source.parents or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=render['sha256']:
        raise HTTPException(409,'Rendered file missing or changed; render again')
    credit='\n'.join(a.get('credit','') for a in data['assets'] if a)
    if len((payload.description+'\n'+credit).encode('utf8'))>4700:raise HTTPException(422,'Shorten description; image credits must fit YouTube limits')
    folder=root/'videos'/key;folder.mkdir(parents=True,exist_ok=True)
    target=folder/'short.mp4';shutil.copyfile(source,target)
    persona=Personality(id=new_id(),workspace_id=row.workspace_id,channel_id=channel.id,
        creator_member_id=member.id,visibility='personal',name=data.get('analysis',{}).get('topic',row.title)[:160])
    db.add(persona);db.flush()
    topic=Topic(id=new_id(),personality_id=persona.id,channel_id=channel.id,title=row.title[:300],
        verification_status='verified',evidence=json.dumps(data.get('sources',[])),source_name='Reviewed title research')
    db.add(topic);db.flush()
    job=VideoJob(id=key,workspace_id=row.workspace_id,channel_id=channel.id,personality_id=persona.id,
        topic_id=topic.id,topic_title=row.title[:300],duration=row.duration,language={'English':'en-US','Urdu':'ur-PK','Roman Urdu':'ur-PK'}[row.language],
        status='ready_for_review',current_step='ready_for_review',research_trace=json.dumps({'title_draft_id':row.id,'draft_revision':row.revision}))
    db.add(job);db.flush()
    narrations=[s['narration'] for s in data['plan']['scenes']]
    script=Script(id=new_id(),job_id=key,hook=narrations[0],context='',main_story=' '.join(narrations[1:-1]),
        why_it_matters='',ending=narrations[-1],full_script=' '.join(narrations))
    db.add(script);db.flush()
    db.add(SEOData(id=new_id(),script_id=script.id,title=payload.title,description=payload.description+'\n'+credit,
        hashtags='["#Shorts"]',keywords='[]',cover_text=payload.title[:80]))
    db.add(Video(id=new_id(),job_id=key,output_path=str(target),thumbnail_path='',duration=render['duration'],media_revision=1))
    audio=root/'title-shorts'/row.id/('render-'+str(render['revision']))/'source.wav'
    audio_target=root/'audio'/(key+'.wav');audio_target.parent.mkdir(exist_ok=True)
    if audio.is_file():shutil.copyfile(audio,audio_target)
    db.add(VoiceGeneration(id=new_id(),job_id=key,provider=data.get('voice',{}).get('provider','Reviewed title narration'),voice='reviewed',output_path=str(audio_target),script_hash=hashlib.sha256(script.full_script.encode()).hexdigest()))
    for i,scene in enumerate(data['plan']['scenes']):
        db.add(Scene(id=new_id(),job_id=key,scene_number=i+1,start_time=scene['start'],end_time=scene['end'],narration=scene['narration'],visual_query=scene['image_query'],visual_type='archival_photo',caption=scene['on_screen_text'],emphasis_word=''))
        asset=data['assets'][i];asset_source=Path(asset['path']).resolve()
        if root not in asset_source.parents or not asset_source.is_file():raise HTTPException(409,'Scene image missing; render again')
        images=root/'images'/key;images.mkdir(parents=True,exist_ok=True)
        image=images/(str(i+1)+asset_source.suffix);shutil.copyfile(asset_source,image)
        db.add(Asset(id=new_id(),job_id=key,scene_number=i+1,source='Reviewed title image',url=asset.get('source_url'),
            creator=asset.get('creator'),license=asset['license'],attribution=asset.get('credit','')[:500],local_path=str(image),
            provenance=json.dumps({'kind':'archive','rights_checked':True,'required_credit':asset.get('credit',''),'library_media_id':asset.get('library_media_id'),'authenticity_note':asset.get('note')})))
    data['video_job_id']=key;row.data=json.dumps(data)
    db.commit()
    return {'job_id':key}
