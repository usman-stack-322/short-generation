import json,sqlite3,collections
from pathlib import Path
root=Path(__file__).resolve().parents[2]
db=sqlite3.connect(root/'backend/ai_shorts.db');db.row_factory=sqlite3.Row
for row in json.loads((root/'generated/fresh-pilots.json').read_text()):
 j=dict(db.execute('select * from video_jobs where id=?',(row['job_id'],)).fetchone());t=json.loads(j['research_trace'])
 print(row['subject'],j['id'],j['status'],j['current_step'],j['error_message'])
 h=t.get('historical_search',{});print({k:v for k,v in h.items() if k not in ['outcomes','discovery']})
 if h:print(collections.Counter(x['status'] for x in h.get('outcomes',[])))
 print('topic:',j['topic_title'])
