import json
from app.database.session import SessionLocal
from app.models import TitleShortDraft
with SessionLocal() as db:
 d=db.get(TitleShortDraft,'97e2bfd4-2c9b-4144-ab64-f410062a05b7');data=json.loads(d.data);print(json.dumps({'status':d.status,'error':d.error_message,'source_count':len(data.get('sources',[])),'plan':data.get('plan'),'analysis':data.get('analysis')},ensure_ascii=False))
