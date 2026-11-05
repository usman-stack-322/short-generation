import os,subprocess,sys,re
from pathlib import Path
root=Path(__file__).resolve().parents[2]
env={**os.environ,'YOUTUBE_UPLOADS_ENABLED':'false','SCHEDULER_ENABLED':'false'}
if '--restart' in sys.argv:
 text=(root/'generated/supervised-backend.log').read_text(errors='replace')
 pid=int(re.findall(r'Started server process \[(\d+)\]',text)[-1])
 subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],check=True,capture_output=True)
log=open(root/'generated/supervised-backend.log','a')
p=subprocess.Popen([str(root/'.venv/Scripts/python.exe'),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--workers','1'],cwd=root/'backend',env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
print(p.pid)
