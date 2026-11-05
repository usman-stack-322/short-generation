import json,httpx,time,shutil
from pathlib import Path
from app.video.alignment import load_boundaries
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/imagery-continuation'
rows=json.loads((OUT/'updated-pilots.json').read_text())
for row in rows:
 audio=OUT/'alignment'/(row['job_id']+'-sapi.wav')
 assert load_boundaries(audio,row['job']['script']['full_script']),row['subject']+' comparison timing invalid'
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=60) as c:
 a=c.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});a.raise_for_status();headers={'Authorization':'Bearer '+a.json()['access_token']}
 for row in rows:
  r=c.post('/api/videos/'+row['job_id']+'/regenerate',headers=headers,json={'scope':'voice'});r.raise_for_status()
 deadline=time.monotonic()+500
 while time.monotonic()<deadline:
  for row in rows:row['job']=c.get('/api/videos/'+row['job_id'],headers=headers).json()
  states=[r['job']['status'] for r in rows];print(states,flush=True)
  if all(s in ['ready_for_review','failed'] for s in states):break
  time.sleep(10)
 for row in rows:
  j=row['job'];assert j['status']=='ready_for_review',j.get('error_message')
  source=ROOT/'generated/videos'/j['id']/'short.mp4';timing=json.loads((source.parent/'subtitle-timing.json').read_text())
  assert timing['word_events']>0 and 'native' in timing['method'].lower()
  folder=OUT/'renders'/j['id']/f"revision-{j['content_revision']}";folder.mkdir(parents=True,exist_ok=True)
  for src in [source,source.parent/'subtitle-timing.json']:shutil.copy2(src,folder/src.name)
  row['new_mp4_path']=str(folder/'short.mp4');row['native_timing']=timing
 (OUT/'updated-pilots.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
