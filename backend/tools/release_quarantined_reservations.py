import json
from pathlib import Path
from app.database.session import SessionLocal
from app.models import Topic
root=Path(__file__).resolve().parents[2]
with SessionLocal() as db:
 for name in ['quarantined-pilot-selection.json','quarantined-henry-related-card.json']:
  snapshot=json.loads((root/'generated'/name).read_text());t=db.get(Topic,snapshot['topic_id'])
  assert t.verification_status=='rejected'
  snapshot['released_event_identity']=t.event_identity
  (root/'generated'/name).write_text(json.dumps(snapshot,indent=2))
  t.event_identity=None
 db.commit()
