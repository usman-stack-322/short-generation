"""Normal authenticated pilot rebuild, one provider synthesis request per subject.

Run Henry first. No purchases, voice creation, uploads to YouTube or schedules.
Rendering retries reuse the committed narration with --render-only.
"""
import argparse
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import httpx
os.environ['YOUTUBE_UPLOADS_ENABLED']='false'
os.environ['SCHEDULER_ENABLED']='false'
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob,LibraryMedia,Asset
from app.services.assets.credits import sync_credits
from app.services.preferences import invalidate_approvals

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/quality-revision/clean-pilots'
IDS={'Henry':'0f4ddd93-61f6-452d-abfb-b4c6f212f3b2','Ronaldo':'230904a6-bfc0-4182-b240-c4d498cd99fe',
     'Messi':'7f51b5de-a19d-4faf-9318-43dc15ba2b06'}
# Avoid showing a later Ronaldo trophy presentation as the 2008 award event.
# Omit the weakest-resolution Messi portrait; retained originals are not deleted.
ORDERS={'Henry':[0,1,2,3,0,2],'Ronaldo':[0,2,1,0,2,1],'Messi':[0,2,3,2,0,3]}
VOICE='JBFqnCBsd6RMkjVDRZzb'


def main(subject,render_only=False):
    OUT.mkdir(parents=True,exist_ok=True);jid=IDS[subject]
    marker=OUT/f'{subject.lower()}-voice-request.json'
    if subject!='Henry' and not render_only:
        check=json.loads((OUT/'henry-verified.json').read_text(encoding='utf8'))
        if not check.get('available_checks_passed'):raise RuntimeError('Inspect Henry before rebuilding the others')
    if marker.exists() and not render_only:
        raise RuntimeError('Voice request already recorded; use --render-only to avoid another synthesis request')
    if not render_only:
        inventory=json.loads((ROOT/'generated/quality-revision/generic-voices.json').read_text(encoding='utf8'))
        assert any(v['voice_id']==VOICE and v['category']=='premade' for v in inventory['voices'])
        q=httpx.get('https://api.elevenlabs.io/v1/user/subscription',headers={'xi-api-key':settings.elevenlabs_api_key},timeout=30)
        q.raise_for_status();quota=q.json()
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=90) as client:
        login=client.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'})
        login.raise_for_status();headers={'Authorization':'Bearer '+login.json()['access_token']}
        config=client.get('/api/settings',headers=headers).json();assert config['uploads_enabled'] is False
        response=client.get('/api/videos/'+jid,headers=headers);response.raise_for_status();job=response.json()
        if not render_only:
            before=OUT/jid/f"before-cloud-revision-{job['content_revision']}";before.mkdir(parents=True,exist_ok=True)
            (before/'job.json').write_text(json.dumps(job,indent=2),encoding='utf8')
            with SessionLocal() as db:
                record=db.get(VideoJob,jid)
                for source in [Path(record.video.output_path),Path(record.voice_generation.output_path),
                    ROOT/'generated/audio'/f'{jid}.words.json',ROOT/'generated/thumbnails'/f'{jid}.png']:
                    if source.is_file() and not (before/source.name).exists():shutil.copy2(source,before/source.name)
            if subject=='Henry':
                script={k:job['script'][k] for k in ('hook','context','main_story','why_it_matters','ending')}
                old=dict(script)
                script.update(hook="In 2004, Thierry Henry's fellow players chose him again.",
                    context='He was named the English PFA Player of the Year.',main_story='It was his second season running.')
                (before/'script-edit.json').write_text(json.dumps({'before':old,'after':script,
                    'reason':'Replace vague opening/context with existing verified year, peer recognition, award and second-consecutive-season facts. No new fact introduced.'},indent=2),encoding='utf8')
                if script!=old:
                    response=client.patch('/api/videos/'+jid+'/script',headers=headers,json=script)
                    response.raise_for_status();job=response.json()
            text=job['script']['full_script']
            remaining=int(quota['character_limit'])-int(quota['character_count'])
            if remaining<len(text)+30:raise RuntimeError('Existing quota is insufficient; no purchase or synthesis requested')
            photos=[p for p in json.loads((ROOT/'generated/imagery-continuation/curated-photos.json').read_text(encoding='utf8'))
                    if p['subject']==subject and 'error' not in p]
            assignments=[]
            for scene,index in enumerate(ORDERS[subject],1):
                photo=photos[index];path=Path(photo['path'])
                if photo.get('sha256') and hashlib.sha256(path.read_bytes()).hexdigest()!=photo['sha256']:
                    raise RuntimeError('Retained photo hash changed')
                asset=next(a for a in job['assets'] if a['scene_number']==scene)
                with SessionLocal() as db:
                    current=db.get(Asset,asset['id']);preview=Path(current.local_path)
                    already_prepared=(current.url==photo['source_url'] and current.license==photo['license']
                        and current.creator==photo['creator'] and preview.with_name(preview.stem+'-source.jpg').is_file())
                if already_prepared:
                    assignments.append(photo)
                    continue
                data={'revision':job['content_revision'],'creator':photo['creator'],'license':photo['license'],
                    'source_url':photo['source_url'],'rights_confirmed':'true','real_photo_confirmed':'true',
                    'capture_date':photo['capture_date'],'source_title':photo['title']}
                result=client.post(f'/api/videos/{jid}/assets/{asset["id"]}/upload',headers=headers,data=data,
                    files={'file':(path.name,path.read_bytes(),'image/jpeg')})
                result.raise_for_status();job=result.json();assignments.append(photo)
            with SessionLocal() as db:
                record=db.get(VideoJob,jid);invalidate_approvals(db,record);record.media_revision+=1
                record.tts_provider='elevenlabs';record.voice=VOICE;record.voice_style='documentary'
                if subject!='Henry':record.duration=max(record.duration,45)
                trace=json.loads(record.research_trace or '{}');trace['manual_scene_timing']=False
                trace['approved_narrator']={'voice_id':VOICE,'name':'George - Warm, Captivating Storyteller','category':'premade',
                    'model':'eleven_multilingual_v2','basis':'User-approved audition and current Henry-first audio revision request'}
                record.research_trace=json.dumps(trace)
                current_assets=db.query(Asset).filter_by(job_id=jid).order_by(Asset.scene_number).all()
                for asset,photo in zip(current_assets,assignments):
                    meta=json.loads(asset.provenance);meta.update(focal_x=.5,focal_y=.18)
                    meta['required_credit']=meta['required_credit'].replace('Resized proportionally, padded and labeled; gentle pan/zoom',
                        'Original photo reframed with proportional crop or same-photo blurred backdrop and restrained camera movement; box-free subtitles')
                    meta['modifications']='Original crop or same-photo blur backdrop; movement; no archive label or caption panel'
                    asset.provenance=json.dumps(meta)
                if record.script.seo:
                    disclosure='Archival photographs illustrate the player; they do not depict the historical award event. '
                    if not record.script.seo.description.startswith(disclosure):record.script.seo.description=disclosure+record.script.seo.description
                sync_credits(db,record)
                approved_clips=db.query(LibraryMedia).filter_by(personality_id=record.personality_id,media_type='clip',approved=True,archived=False).count()
                db.commit()
            marker.write_text(json.dumps({'subject':subject,'voice_id':VOICE,'voice_name':'George - Warm, Captivating Storyteller',
                'model':'eleven_multilingual_v2','characters':len(text),'quota_before':{'used':quota['character_count'],'limit':quota['character_limit'],'tier':quota.get('tier',quota.get('status'))},
                'provider_requests_scheduled':1,'do_not_retry_voice_automatically':True,'approved_library_clips':approved_clips,
                'selected_photo_sources':[{'title':p['title'],'url':p['source_url'],'date':p['capture_date'],'license':p['license'],'creator':p['creator']} for p in assignments]},indent=2),encoding='utf8')
        else:
            with SessionLocal() as db:
                record=db.get(VideoJob,jid)
                if record.voice_generation.provider!='ElevenLabs allowed narrator' or record.voice_generation.script_hash!=hashlib.sha256(record.script.full_script.encode()).hexdigest():
                    raise RuntimeError('Complete approved cloud narration is not committed; refusing a render-only fallback')
        result=client.post('/api/videos/'+jid+'/regenerate',headers=headers,json={'scope':'video' if render_only else 'voice','voice_style':'documentary'} if not render_only else {'scope':'video'})
        result.raise_for_status()
        deadline=time.monotonic()+1500
        while time.monotonic()<deadline:
            response=client.get('/api/videos/'+jid,headers=headers);response.raise_for_status();job=response.json()
            print(subject,job['status'],flush=True)
            if job['status'] in {'ready_for_review','failed'}:break
            time.sleep(10)
        (OUT/f'{subject.lower()}-job.json').write_text(json.dumps(job,indent=2),encoding='utf8')
        if job['status']!='ready_for_review':raise RuntimeError(job.get('error_message') or 'Render timeout')
        with SessionLocal() as db:
            record=db.get(VideoJob,jid);path=Path(record.video.output_path)
            summary={'subject':subject,'job_id':jid,'revision':record.content_revision,'media_revision':record.media_revision,
                'mp4_path':str(path),'review_url':'http://127.0.0.1:5173/videos/'+jid,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'provider':record.voice_generation.provider,'voice':record.voice_generation.voice,'voice_name':'George - Warm, Captivating Storyteller',
                'model':'eleven_multilingual_v2','direct_listening':False,'photo_scenes':db.query(Asset).filter_by(job_id=jid).count(),'distinct_photos':len(set(ORDERS[subject])),
                'clips':0,'standalone_cards':0,'drawn_archive_labels':0,'caption_panels':0,'approval_count':job['approval_count'],
                'audio_processing':json.loads((path.parent/'audio-processing.json').read_text(encoding='utf8')),
                'timeline':json.loads((path.parent/'render-timeline.json').read_text(encoding='utf8'))}
        (OUT/f'{subject.lower()}-candidate.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
        print(json.dumps({k:summary[k] for k in ('subject','revision','mp4_path','provider')},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--subject',choices=IDS,default='Henry');parser.add_argument('--render-only',action='store_true')
    args=parser.parse_args();main(args.subject,args.render_only)
