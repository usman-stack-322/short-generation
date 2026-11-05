import json,hashlib
from pathlib import Path
from sqlalchemy import text,inspect
from app.database.session import engine,SessionLocal
from app.core.config import settings
from app.models import VideoJob,TitleShortDraft
root=Path(__file__).resolve().parents[2];rows=[]
for id,revision,sha in [('230904a6-bfc0-4182-b240-c4d498cd99fe',21,'289a80919c5d0bc30bc6ca9afd8cc1591380d8eed2d0f6639f265c33059b64b3'),('7f51b5de-a19d-4faf-9318-43dc15ba2b06',20,'7908117a4bf7e0398add424663a6d589fe76af25327c2cd8cb77e53529fad55f'),('0f4ddd93-61f6-452d-abfb-b4c6f212f3b2',32,'621835aa62ddc68b3030509037c0243c9eb58d475ad7e3a7fc69122c41570449')]:
 with SessionLocal() as db:
  job=db.get(VideoJob,id);p=Path(job.video.output_path);row={'id':id,'revision':job.content_revision,'expected_revision':revision,'hash_matches':hashlib.sha256(p.read_bytes()).hexdigest()==sha};assert row['revision']==revision and row['hash_matches'];rows.append(row)
with engine.connect() as c:version=c.execute(text('select version_num from alembic_version')).scalar()
assert version=='0014_title_shorts' and not settings.youtube_uploads_enabled and not settings.scheduler_enabled
result={'migration':version,'pilot_preservation':rows,'uploads_disabled':not settings.youtube_uploads_enabled,'scheduler_disabled':not settings.scheduler_enabled,'title_table_exists':'title_short_drafts' in inspect(engine).get_table_names()}
(root/'generated/title-to-short-verification/installation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
