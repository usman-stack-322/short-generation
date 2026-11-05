import json
from app.database.session import SessionLocal
from app.models import Asset
with SessionLocal() as db:
 a=db.query(Asset).filter_by(job_id='230904a6-bfc0-4182-b240-c4d498cd99fe').first();print(json.dumps({'path':a.local_path,'license':a.license,'url':a.url,'metadata':json.loads(a.provenance)},indent=2))
