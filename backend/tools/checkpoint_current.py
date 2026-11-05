import os,json
os.environ['YOUTUBE_UPLOADS_ENABLED']='false'
os.environ['SCHEDULER_ENABLED']='false'
from app.database.session import SessionLocal
from app.models import VideoJob
from app.core.config import settings
with SessionLocal() as db:
 for jid in ['230904a6-bfc0-4182-b240-c4d498cd99fe','7f51b5de-a19d-4faf-9318-43dc15ba2b06','0f4ddd93-61f6-452d-abfb-b4c6f212f3b2']:
  j=db.get(VideoJob,jid)
  print(json.dumps(dict(id=jid,revision=j.content_revision,path=j.video.output_path,status=j.status,provider=j.voice_generation.provider,voice=j.voice_generation.voice,duration=j.video.duration)))
print('ffmpeg',settings.ffmpeg_path)
