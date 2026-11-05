import json,httpx
from pathlib import Path
root=Path(__file__).resolve().parents[2]
rows=json.loads((root/'generated/fresh-pilots.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8000/api',timeout=30) as c:
 a=c.post('/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});a.raise_for_status();c.headers['Authorization']='Bearer '+a.json()['access_token']
 for row in rows:
  state=c.get('/videos/'+row['job_id']).json()['status']
  if state not in ['research_ready','failed','verification_required']:
   print(row['subject'],state,'left running or complete');continue
  r=c.post('/videos/'+row['job_id']+'/regenerate',json={'scope':'retry'});r.raise_for_status();print(row['subject'],r.json()['status'])
