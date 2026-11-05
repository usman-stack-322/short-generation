import json
from pathlib import Path
from app.database.session import SessionLocal
from app.models import VideoJob
with SessionLocal() as db:
 j=db.get(VideoJob,'0f4ddd93-61f6-452d-abfb-b4c6f212f3b2')
 assert j.status=='research_ready' and not j.script and not j.video
 assert j.topic.title.startswith('Historical: Live ')
 Path('../generated/quarantined-henry-related-card.json').write_text(json.dumps({'topic_id':j.topic.id,'title':j.topic.title,'evidence':json.loads(j.topic.evidence)},indent=2))
 j.topic.verification_status='rejected';j.topic=None;j.topic_title='';j.status='failed';j.failed_step='researching';j.current_step='interrupted';j.error_message='Related-news card excluded; retry substantive article research.'
 db.commit()
