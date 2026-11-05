import json
from app.database.session import SessionLocal
from app.models import TitleShortDraft
with SessionLocal() as db:
 d=db.get(TitleShortDraft,'83aed818-f7ff-489f-80fc-4573f844d628');x=json.loads(d.data)
 print(json.dumps({'revision':d.revision,'status':d.status,'error':d.error_message,'scope':x.get('scope'),'review':x.get('evidence_review'),'plan':x.get('plan'),'rejected_plans':x.get('rejected_plans',[])[-2:]},indent=2))
