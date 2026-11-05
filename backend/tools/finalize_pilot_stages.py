import json,httpx
from pathlib import Path
rows=json.loads((Path(__file__).resolve().parents[2]/'generated/fresh-pilots.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8000/api',timeout=30) as c:
 a=c.post('/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});a.raise_for_status();c.headers['Authorization']='Bearer '+a.json()['access_token']
 for row in rows:
  j=c.get('/videos/'+row['job_id']).json()
  scope='video' if j['status']=='ready_for_review' else 'retry'
  r=c.post('/videos/'+row['job_id']+'/regenerate',json={'scope':scope});r.raise_for_status();print(row['subject'],scope,r.json()['status'])
