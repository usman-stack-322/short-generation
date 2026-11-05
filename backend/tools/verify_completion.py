"""Read-only normal-app media and pilot evidence. Never invokes providers."""
import json
from pathlib import Path
import subprocess
import httpx
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob

root=Path(__file__).resolve().parents[2]
pilot_file=root/'generated'/'implementation-pilot.json'
pilot=json.loads(pilot_file.read_text())
result={'existing_media':[], 'pilot':[], 'uploads_disabled':not settings.youtube_uploads_enabled}
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=60) as client:
    auth=client.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'})
    auth.raise_for_status();headers={'Authorization':'Bearer '+auth.json()['access_token']}
    before=client.get('/api/videos',headers=headers).json()
    for entry in pilot['attempts']:
        job=client.get('/api/videos/'+entry['job_id'],headers=headers).json()
        info={**entry,'status':job['status'],'error':job.get('error_message'),'trace':job.get('research_trace'),'script_present':bool(job.get('script')),'narration_present':bool(job.get('narration_url')),'video_present':bool(job.get('video_url')),'source_reasons':[s.get('reason') for s in job.get('sources',[]) if s.get('reason')]}
        result['pilot'].append(info)
    for job in before:
        if not job.get('video_url'):continue
        response=client.get(job['video_url']+'&download=true',headers=headers)
        info={'job_id':job['id'],'review_url':'http://127.0.0.1:5173/videos/'+job['id'],'status':response.status_code,'bytes':len(response.content),'content_type':response.headers.get('content-type'),'attachment':response.headers.get('content-disposition')}
        with SessionLocal() as db:
            record=db.get(VideoJob,job['id'])
            path=Path(record.video.output_path)
            info['mp4_path']=str(path)
            info['narration_path']=record.voice_generation.output_path if record.voice_generation else None
            if path.is_file():
                probe=subprocess.run([settings.ffprobe_path,'-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',str(path)],capture_output=True,text=True)
                info['probe']=json.loads(probe.stdout) if probe.returncode==0 else probe.stderr
        result['existing_media'].append(info)
    after=client.get('/api/videos',headers=headers).json()
    result['read_did_not_generate']=len(before)==len(after) and {j['id']:j['status'] for j in before}=={j['id']:j['status'] for j in after}
(root/'generated'/'implementation-normal-workflow.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'existing_media':[{k:r[k] for k in ('job_id','status','bytes')} for r in result['existing_media']],'pilot':[{k:r[k] for k in ('subject','status','error')} for r in result['pilot']],'read_did_not_generate':result['read_did_not_generate']},indent=2))
