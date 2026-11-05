"""Assign reviewed distinct photos and regenerate existing pilots, no new topics."""
import json,time,httpx,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/imagery-continuation'
IDS={'Ronaldo':'230904a6-bfc0-4182-b240-c4d498cd99fe','Messi':'7f51b5de-a19d-4faf-9318-43dc15ba2b06','Henry':'0f4ddd93-61f6-452d-abfb-b4c6f212f3b2'}
photos=json.loads((OUT/'curated-photos.json').read_text());results=[]
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=60) as c:
 a=c.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});a.raise_for_status();headers={'Authorization':'Bearer '+a.json()['access_token']}
 assert c.get('/api/settings',headers=headers).json()['uploads_enabled'] is False
 for subject,jid in IDS.items():
  job=c.get('/api/videos/'+jid,headers=headers).json();before=job['script'];assignments=[]
  selected=[p for p in photos if p['subject']==subject and 'error' not in p]
  assert len(selected)==4 and len({p['sha256'] for p in selected})==4
  for scene,p in zip([1,3,4,6],selected):
   asset=next(a for a in job['assets'] if a['scene_number']==scene)
   data={'revision':job['content_revision'],'creator':p['creator'],'license':p['license'],'source_url':p['source_url'],'rights_confirmed':'true','real_photo_confirmed':'true','capture_date':p['capture_date'],'source_title':p['title']}
   r=c.post(f'/api/videos/{jid}/assets/{asset["id"]}/upload',headers=headers,data=data,files={'file':(Path(p['path']).name,Path(p['path']).read_bytes(),'image/jpeg')});r.raise_for_status();job=r.json()
   assignments.append({'scene':scene,'photo':p,'asset_id':asset['id']})
  assert job['script']==before and job['approval_count']==0
  r=c.post('/api/videos/'+jid+'/regenerate',headers=headers,json={'scope':'voice'});r.raise_for_status()
  results.append({'subject':subject,'job_id':jid,'assignments':assignments,'script_sha256':hashlib.sha256(before['full_script'].encode()).hexdigest()})
  print(subject,'four photos assigned; voice/video queued',flush=True)
 (OUT/'updated-pilots.json').write_text(json.dumps(results,indent=2),encoding='utf8')
 deadline=time.monotonic()+600
 while time.monotonic()<deadline:
  for row in results:
   r=c.get('/api/videos/'+row['job_id'],headers=headers);r.raise_for_status();row['job']=r.json()
  (OUT/'updated-pilots.json').write_text(json.dumps(results,indent=2),encoding='utf8')
  states=[r['job']['status'] for r in results];print(states,flush=True)
  if all(s in ['ready_for_review','failed'] for s in states):break
  time.sleep(10)
 for row in results:
  j=row['job']
  if j['status']!='ready_for_review':continue
  folder=OUT/'renders'/j['id']/f"revision-{j['content_revision']}";folder.mkdir(parents=True,exist_ok=True)
  source=ROOT/'generated/videos'/j['id']/'short.mp4';destination=folder/'short.mp4';shutil.copy2(source,destination)
  shutil.copy2(source.parent/'subtitle-timing.json',folder/'subtitle-timing.json')
  row['new_mp4_path']=str(destination)
 (OUT/'updated-pilots.json').write_text(json.dumps(results,indent=2),encoding='utf8')
