import json, sqlite3, collections
from pathlib import Path
root=Path(__file__).resolve().parents[2]
db=sqlite3.connect(root/'backend/ai_shorts.db');db.row_factory=sqlite3.Row
out=[]
for jid in ['d10771ad-506f-4931-9e96-367908145336','d8706d5b-9add-4481-9567-e5e0685c2799','0eb9a0be-aef2-47d6-a357-a36267f22f9f']:
 j=dict(db.execute('select * from video_jobs where id=?',(jid,)).fetchone());t=json.loads(j['research_trace']);ids=t.get('candidate_ids',[])
 rows=[dict(r) for r in db.execute('select * from research_candidates where id in ('+','.join('?'*len(ids))+')',ids)]
 out.append({'id':jid,'status':j['status'],'step':j['current_step'],'failed_step':j['failed_step'],'error':j['error_message'],'settings':t.get('generation_settings'),'historical':t.get('historical_search'),'reasons':dict(collections.Counter(r['rejection_reason'] for r in rows)), 'historical_candidates':[json.loads(r['data']) for r in rows if json.loads(r['data']).get('content_type')=='historical']})
(root/'generated/pilot-blocker-investigation.json').write_text(json.dumps(out,indent=2))
for r in out:
 print(json.dumps({k:v for k,v in r.items() if k not in {'historical_candidates','historical'}}))
 print(json.dumps(r['historical']))
