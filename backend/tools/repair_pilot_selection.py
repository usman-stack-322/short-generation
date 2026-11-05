"""Quarantine the one evidenced wrong-subject selection; retain its audit record."""
import json
from pathlib import Path
from app.database.session import SessionLocal
from app.models import VideoJob
root=Path(__file__).resolve().parents[2]
with SessionLocal() as db:
 j=db.get(VideoJob,'230904a6-bfc0-4182-b240-c4d498cd99fe')
 assert j.status=='failed' and j.script is None and j.video is None
 assert 'Lionel Messi has won' in j.topic.title
 snapshot={'job_id':j.id,'topic_id':j.topic.id,'topic_title':j.topic.title,'evidence':json.loads(j.topic.evidence),'trace':json.loads(j.research_trace)}
 (root/'generated/quarantined-pilot-selection.json').write_text(json.dumps(snapshot,indent=2))
 j.topic.verification_status='rejected'
 t=json.loads(j.research_trace);t['invalidated_selection']={'topic_id':j.topic.id,'reason':'Subject only mentioned as previous winner; historical focus defect corrected'}
 j.research_trace=json.dumps(t);j.topic=None;j.topic_title='';j.failed_step='researching'
 j.error_message='Wrong-subject selection quarantined. Retry research using direct subject references.'
 db.commit();print(j.id,'held for corrected research')
