import os,json
from pathlib import Path
os.environ['YOUTUBE_UPLOADS_ENABLED']='false';os.environ['SCHEDULER_ENABLED']='false'
from app.database.session import SessionLocal
from app.models import LibraryMedia,VideoJob
from app.core.config import settings
import httpx
result={'youtube_uploads_enabled':settings.youtube_uploads_enabled,'scheduler_enabled':settings.scheduler_enabled,'google_tts_configured':bool(settings.google_tts_api_key or settings.google_application_credentials),'cloud_synthesis_requests':0}
with SessionLocal() as db:
 j=db.get(VideoJob,'0f4ddd93-61f6-452d-abfb-b4c6f212f3b2')
 result['approved_henry_clips']=db.query(LibraryMedia).filter_by(personality_id=j.personality_id,media_type='clip',approved=True,archived=False).count()
 result['normal_revisions']={key:db.get(VideoJob,value).content_revision for key,value in {'Ronaldo':'230904a6-bfc0-4182-b240-c4d498cd99fe','Messi':'7f51b5de-a19d-4faf-9318-43dc15ba2b06','Henry':'0f4ddd93-61f6-452d-abfb-b4c6f212f3b2'}.items()}
if settings.elevenlabs_api_key:
 try:
  r=httpx.get('https://api.elevenlabs.io/v1/user/subscription',headers={'xi-api-key':settings.elevenlabs_api_key},timeout=30);r.raise_for_status();q=r.json()
  result['elevenlabs_read_only_quota']={k:q.get(k) for k in ['tier','character_count','character_limit','can_extend_character_limit']}
 except Exception as e:result['elevenlabs_read_only_quota_error']=type(e).__name__
else:result['elevenlabs_read_only_quota']='not configured'
p=Path(__file__).resolve().parents[2]/'generated/hybrid-review/availability.json';p.write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
