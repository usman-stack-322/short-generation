"""Final comparable auditions; retain all earlier attempts separately."""
import json,subprocess,time,sys,concurrent.futures
from pathlib import Path
PYTHON=Path(r'C:/Users/ua589/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
PASSAGES={
 'hook':"Back-to-back awards. What does that say about a player? In 2004, Thierry Henry's fellow players chose him again.",
 'serious':"This was recognition from fellow professionals. The story is about an individual award, rather than a single match result.",
 'achievement':"Thierry Henry was named the English PFA Player of the Year. It was his second season in a row. Two seasons. The same honour."}
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'generated/hybrid-review';OUT=BASE/'comparison-v2';OUT.mkdir(exist_ok=True)

def sample(item):
 voice,purpose,text=item;output=OUT/(voice+'-'+purpose+'.wav');t=time.perf_counter()
 if voice=='sapi_david':
  command=[sys.executable,'-m','app.tts.local_worker',str(output),'Microsoft David Desktop - English (United States)','1','1'];payload=text
 else:
  command=[str(PYTHON),'-m','app.tts.kokoro_worker'];payload=json.dumps({'runtime':str(BASE),'voice':voice,'text':text,'output':str(output),'speed':1,'alignment_required':False})
 result=subprocess.run(command,input=payload,encoding='utf8',capture_output=True,timeout=240)
 row={'voice':voice,'passage':purpose,'text':text,'path':str(output),'wall_seconds':time.perf_counter()-t,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr[-2000:]}
 print(json.dumps(row),flush=True);(OUT/(voice+'-'+purpose+'.result.json')).write_text(json.dumps(row,indent=2));return row

if __name__=='__main__':
 items=[(v,p,t) for v in ['bm_george','bf_emma','sapi_david'] for p,t in PASSAGES.items()]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:results=list(ex.map(sample,items))
 (BASE/'final-voice-comparison.json').write_text(json.dumps(results,indent=2))
 if any(r['exit'] for r in results):raise RuntimeError('Some auditions failed; inspect real results')
