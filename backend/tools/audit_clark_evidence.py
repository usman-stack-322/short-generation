import json
from pathlib import Path
from app.database.session import SessionLocal
from app.models import TitleShortDraft
from app.services.title_shorts import ai
from app.services.title_evidence import verify_incident
with SessionLocal() as db:
 d=db.get(TitleShortDraft,'83aed818-f7ff-489f-80fc-4573f844d628');data=json.loads(d.data)
 def capture(prompt,schema):
  result=ai(prompt,schema);Path('../generated/automatic-research-clark/audit-proposal.json').write_text(json.dumps(result,indent=2));return result
 try:
  result=verify_incident(d,data,capture);print(json.dumps(result,indent=2))
 except Exception as e:print(type(e).__name__,str(e))
