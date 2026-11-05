import json,httpx
from pathlib import Path
from sqlalchemy import func
from app.database.session import SessionLocal
from app.models import TitleShortDraft
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as c:
 r=c.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});r.raise_for_status();h={'Authorization':'Bearer '+r.json()['access_token']}
 with SessionLocal() as db:before=db.query(TitleShortDraft).count()
 results=[]
 for language in ['Urdu','Roman Urdu']:
  r=c.post('/api/title-shorts',headers=h,json={'title':'One source-backed topic','language':language,'narrator':'local'});results.append({'language':language,'status':r.status_code,'detail':r.json()['detail']});assert r.status_code==422
 r=c.post('/api/title-shorts',headers=h,json={'title':'One source-backed topic','source_urls':['http://127.0.0.1/private']});assert r.status_code==422
 with SessionLocal() as db:after=db.query(TitleShortDraft).count()
 assert before==after
 settings=c.get('/api/settings',headers=h).json();assert settings['uploads_enabled'] is False
 data={'narrator_preflight':results,'private_url_rejected':True,'no_jobs_allocated':before==after,'uploads_disabled':True}
 Path('../generated/title-short-live/api-preflight.json').write_text(json.dumps(data,indent=2));print(json.dumps(data,indent=2))
