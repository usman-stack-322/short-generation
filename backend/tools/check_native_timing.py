import json,hashlib,re
from pathlib import Path
from app.core.config import settings
ROOT=Path(__file__).resolve().parents[2]
rows=json.loads((ROOT/'generated/imagery-continuation/updated-pilots.json').read_text())
for row in rows:
 j=row['job'];audio=Path(settings.generated_dir)/'audio'/f"{j['id']}.wav";path=audio.with_suffix('.words.json');script=j['script']['full_script']
 data=json.loads(path.read_text());words=data['words']
 missing=[{'word':m.group(),'char':m.start(),'nearby':[w for w in words if abs(w['char']-m.start())<8]} for m in re.finditer(r'\w+',script) if not any(w['char']<=m.start()<w['char']+w['length'] for w in words)]
 bad=[w for i,w in enumerate(words) if not 0<=w['start']<=data['duration'] or (i and w['start']<words[i-1]['start']) or not 0<=w['char']<w['char']+w['length']<=len(script)]
 print(row['subject'],'script hash',data['script_sha256']==hashlib.sha256(script.encode()).hexdigest(),'audio hash',data['audio_sha256']==hashlib.sha256(audio.read_bytes()).hexdigest(),'duration',data['duration'],'missing',missing,'bad',bad)
