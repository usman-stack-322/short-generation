import json,httpx
from pathlib import Path
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import ChannelAuthorization,LibraryMedia,VideoJob
root=Path(__file__).resolve().parents[2];out=root/'generated/motion-continuation'
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as c:
 r=c.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});r.raise_for_status();h={'Authorization':'Bearer '+r.json()['access_token']}
 config=c.get('/api/settings',headers=h).json()
 snapshot={'uploads_enabled':config['uploads_enabled'],'scheduler_enabled':settings.scheduler_enabled,'providers':config['providers'],'oauth_callback':settings.google_redirect_uri,'token_encryption_configured':bool(settings.token_encryption_key),'durable_external_worker':False,'runtime_worker':'one serialized in-process worker','publishing_actions_performed':False}
 with SessionLocal() as db:
  snapshot['authorization_records']=db.query(ChannelAuthorization).count()
  snapshot['approved_library_clips']=db.query(LibraryMedia).filter_by(media_type='clip',approved=True,archived=False).count()
  snapshot['pilot_approved_clips']={}
  for row in json.loads((out/'pilots.json').read_text()):
   j=db.get(VideoJob,row['job_id'])
   snapshot['pilot_approved_clips'][row['subject']]=db.query(LibraryMedia).filter_by(personality_id=j.personality_id,media_type='clip',approved=True,archived=False).count()
 (out/'publishing-readiness.json').write_text(json.dumps(snapshot,indent=2),encoding='utf8');print(json.dumps(snapshot,indent=2))
