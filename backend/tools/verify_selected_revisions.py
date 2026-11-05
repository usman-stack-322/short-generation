import os,json,hashlib,subprocess
from pathlib import Path
import httpx
os.environ['YOUTUBE_UPLOADS_ENABLED']='false';os.environ['SCHEDULER_ENABLED']='false'
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob,Asset,Scene
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'generated/hybrid-review';items=json.loads((BASE/'selected-revisions.json').read_text());results=[]
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=90) as c:
 r=c.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});r.raise_for_status();h={'Authorization':'Bearer '+r.json()['access_token']}
 assert c.get('/api/settings',headers=h).json()['uploads_enabled'] is False
 for item in items:
  j=c.get('/api/videos/'+item['normal_job_id'],headers=h);j.raise_for_status();j=j.json()
  assert j['content_revision']==item['normal_revision'] and j['approval_count']==0
  r=c.get(j['video_url']+'&download=true',headers=h);r.raise_for_status();target=BASE/'verification'/item['subject'].lower()/'normal-api-download.mp4';target.write_bytes(r.content)
  decode=subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(target),'-f','null','-'],capture_output=True,text=True,timeout=180)
  row={'subject':item['subject'],'revision':j['content_revision'],'download_status':r.status_code,'hash_matches':hashlib.sha256(r.content).hexdigest()==item['sha256'],'full_download_decode_exit':decode.returncode,'anonymous_status':httpx.get('http://127.0.0.1:8000'+j['video_url'],timeout=30).status_code,'range_status':c.get(j['video_url'],headers={**h,'Range':'bytes=10000-19999'}).status_code,'approval_count':j['approval_count'],'uploads_enabled':False,'script_hash_matches':hashlib.sha256(j['script']['full_script'].encode()).hexdigest()==item['script_sha256'],'actual_voice':j['narrator_voice']}
  with SessionLocal() as db:
   job=db.get(VideoJob,item['normal_job_id']);row['asset_count']=db.query(Asset).filter_by(job_id=job.id).count();row['scene_count']=db.query(Scene).filter_by(job_id=job.id).count();row['distinct_assets']=len(set(a.url for a in db.query(Asset).filter_by(job_id=job.id)))
  assert all([row['hash_matches'],row['script_hash_matches'],row['full_download_decode_exit']==0,row['actual_voice']=='bm_george',row['asset_count']==row['scene_count']==row['distinct_assets']==3,row['anonymous_status']==401,row['range_status']==206])
  results.append(row);print(json.dumps(row),flush=True)
with SessionLocal() as db:
 h=db.get(VideoJob,'0f4ddd93-61f6-452d-abfb-b4c6f212f3b2');assert h.content_revision==32
 assert hashlib.sha256(Path(h.video.output_path).read_bytes()).hexdigest()=='621835aa62ddc68b3030509037c0243c9eb58d475ad7e3a7fc69122c41570449'
assert hashlib.sha256((BASE/'pilot/videos/henry-local-review/revision-2/short.mp4').read_bytes()).hexdigest()=='ce0bba1ab73a98caaeb4fc1fc2ebdb2ac6c8fda29425d9fd5e4b27ec2fbbc40f'
(BASE/'selected-revision-verification.json').write_text(json.dumps({'videos':results,'henry_r32_unchanged':True,'henry_reference_unchanged':True},indent=2))
