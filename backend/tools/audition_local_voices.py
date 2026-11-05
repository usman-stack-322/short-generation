"""Same passages, three generic local voices; no paid requests."""
import json,subprocess,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/hybrid-review';SAMPLES=OUT/'samples';SAMPLES.mkdir(exist_ok=True)
PYTHON=Path(r'C:/Users/ua589/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
PASSAGES={
 'hook':"Back-to-back awards. What does that say about a player? In 2004, Thierry Henry's fellow players chose him again.",
 'serious':"This was recognition from fellow professionals. The story is about an individual award, rather than a single match result.",
 'achievement':"Thierry Henry was named the English PFA Player of the Year. It was his second season in a row. Two seasons. The same honour."}
results=[]
for voice in ['bm_george','bf_emma','sapi_david']:
 for purpose,text in PASSAGES.items():
  output=SAMPLES/(voice+'-'+purpose+'.wav');t=time.perf_counter()
  if voice=='sapi_david':
   cmd=[sys.executable,'-m','app.tts.local_worker',str(output),'Microsoft David Desktop - English (United States)','1.0','1.0'];payload=text
  else:
   cmd=[str(PYTHON),'-m','app.tts.kokoro_worker'];payload=json.dumps({'runtime':str(OUT),'voice':voice,'text':text,'output':str(output),'speed':1,'alignment_required':False})
  run=subprocess.run(cmd,input=payload,encoding='utf8',capture_output=True,timeout=180)
  row={'voice':voice,'purpose':purpose,'text':text,'path':str(output),'wall_seconds':time.perf_counter()-t,'exit':run.returncode,'details':run.stdout,'error':run.stderr[-1500:]}
  results.append(row);(OUT/'voice-comparison.json').write_text(json.dumps(results,indent=2));print(json.dumps(row),flush=True)
