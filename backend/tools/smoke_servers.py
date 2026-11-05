"""Temporary loopback-only UI smoke servers using a copied database. Ctrl+C stops both."""
import os,sys,sqlite3,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
out=ROOT/'generated'/'release-final-smoke';out.mkdir(exist_ok=True)
with sqlite3.connect(ROOT/'backend'/'ai_shorts.db') as source,sqlite3.connect(out/'smoke.db') as target:source.backup(target)
env={**os.environ,'DATABASE_URL':'sqlite:///'+(out/'smoke.db').as_posix(),'SEED_DEMO':'false','SCHEDULER_ENABLED':'false','YOUTUBE_UPLOADS_ENABLED':'false','FRONTEND_ORIGIN':'http://127.0.0.1:5186','VITE_API_URL':'http://127.0.0.1:8026'}
processes=[];logs=[]
try:
    for command,cwd,name in [([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8026'],ROOT/'backend','backend'),(['npm.cmd','run','dev','--','--host','127.0.0.1','--port','5186','--strictPort'],ROOT/'frontend','frontend')]:
        log=(out/(name+'.log')).open('w');logs.append(log)
        processes.append(subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW))
    print('Smoke UI http://127.0.0.1:5186 ; API http://127.0.0.1:8026',flush=True)
    while all(p.poll() is None for p in processes):time.sleep(1)
finally:
    for p in processes:
        if p.poll() is None:p.terminate()
    for log in logs:log.close()
