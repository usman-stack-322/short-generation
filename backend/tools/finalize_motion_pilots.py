import json,time,shutil,httpx
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/motion-continuation';rows=json.loads((OUT/'pilots.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=90) as c:
 a=c.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});a.raise_for_status();h={'Authorization':'Bearer '+a.json()['access_token']}
 for row in rows:
  r=c.post('/api/videos/'+row['job_id']+'/regenerate',headers=h,json={'scope':'video'});r.raise_for_status()
 deadline=time.monotonic()+1200
 while time.monotonic()<deadline:
  for row in rows:row['job']=c.get('/api/videos/'+row['job_id'],headers=h).json()
  states=[x['job']['status'] for x in rows];print(states,flush=True)
  if all(s in ['ready_for_review','failed'] for s in states):break
  time.sleep(10)
 for row in rows:
  j=row['job'];assert j['status']=='ready_for_review',j.get('error_message')
  folder=OUT/j['id']/f"revision-{j['content_revision']}";folder.mkdir(exist_ok=True)
  for src in (ROOT/'generated/videos'/j['id']).iterdir():
   if src.is_file():shutil.copy2(src,folder/src.name)
  row['mp4_path']=str(folder/'short.mp4');print(row['subject'],j['content_revision'],flush=True)
 (OUT/'pilots.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
