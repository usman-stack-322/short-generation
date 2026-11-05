"""Preserve the checkpoint, replace two legacy cards using reviewed photos, rebuild."""
import json,shutil,time,hashlib
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'generated/motion-continuation';OUT.mkdir(exist_ok=True)
rows=json.loads((ROOT/'generated/imagery-continuation/updated-pilots.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=90) as c:
 a=c.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});a.raise_for_status();h={'Authorization':'Bearer '+a.json()['access_token']}
 assert not c.get('/api/settings',headers=h).json()['uploads_enabled']
 for row in rows:
  jid=row['job_id'];j=c.get('/api/videos/'+jid,headers=h).json();folder=OUT/jid/f"before-revision-{j['content_revision']}";folder.mkdir(parents=True,exist_ok=True)
  (folder/'job.json').write_text(json.dumps(j,indent=2),encoding='utf8')
  for src in [ROOT/'generated/videos'/jid/'short.mp4',ROOT/'generated/audio'/f'{jid}.wav',ROOT/'generated/audio'/f'{jid}.words.json',ROOT/'generated/subtitles'/f'{jid}.srt']:
   if src.is_file():shutil.copy2(src,folder/src.name)
  row['before_revision']=j['content_revision'];row['script_hash']=hashlib.sha256(j['script']['full_script'].encode()).hexdigest()
  for scene,p in zip([2,5],[row['assignments'][0]['photo'],row['assignments'][2]['photo']]):
   asset=next(a for a in j['assets'] if a['scene_number']==scene)
   data={'revision':j['content_revision'],'creator':p['creator'],'license':p['license'],'source_url':p['source_url'],'rights_confirmed':'true','real_photo_confirmed':'true','capture_date':p['capture_date'],'source_title':p['title']}
   r=c.post(f'/api/videos/{jid}/assets/{asset["id"]}/upload',headers=h,data=data,files={'file':(Path(p['path']).name,Path(p['path']).read_bytes(),'image/jpeg')});r.raise_for_status();j=r.json()
  r=c.post('/api/videos/'+jid+'/regenerate',headers=h,json={'scope':'voice'});r.raise_for_status();print(row['subject'],'queued',flush=True)
 deadline=time.monotonic()+1500
 while time.monotonic()<deadline:
  for row in rows:row['job']=c.get('/api/videos/'+row['job_id'],headers=h).json()
  (OUT/'pilots.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
  states=[x['job']['status'] for x in rows];print(states,flush=True)
  if all(s in ['ready_for_review','failed'] for s in states):break
  time.sleep(10)
 for row in rows:
  j=row['job'];print(row['subject'],j['status'],j.get('error_message'),flush=True)
  if j['status']!='ready_for_review':continue
  assert hashlib.sha256(j['script']['full_script'].encode()).hexdigest()==row['script_hash']
  assert j['approval_count']==0 and all(a['media_type']=='photo' for a in j['assets'])
  folder=OUT/j['id']/f"revision-{j['content_revision']}";folder.mkdir(exist_ok=True)
  for src in (ROOT/'generated/videos'/j['id']).iterdir():
   if src.is_file():shutil.copy2(src,folder/src.name)
  row['mp4_path']=str(folder/'short.mp4')
 (OUT/'pilots.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
