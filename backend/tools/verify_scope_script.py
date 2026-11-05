import json
from pathlib import Path
from app.database.session import SessionLocal
from app.models import TitleShortDraft
from app.services.title_shorts import check_plan
from app.services.title_scope import accepted
with SessionLocal() as db:
 d=db.get(TitleShortDraft,'83aed818-f7ff-489f-80fc-4573f844d628');data=json.loads(d.data)
 try:
  check_plan(d,data['plan'],data['sources'])
  result={'supported':True,'revision':d.revision,'script':' '.join(s['narration'] for s in data['plan']['scenes']),'scope_accepted':accepted(data),'rendered':False}
 except Exception as exc:result={'supported':False,'error':str(exc),'revision':d.revision}
 Path('../generated/claim-scope-review/final-script-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
