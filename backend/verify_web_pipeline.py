"""Create a NEW current-topic job through the running web API; never approve/upload."""
import json
import time
from pathlib import Path
import httpx
from app.core.config import settings


def main():
    report = {}
    output = Path(settings.generated_dir)/'web-pipeline-verification.json'
    with httpx.Client(base_url='http://127.0.0.1:8000/api',timeout=45) as client:
        login=client.post('/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'})
        login.raise_for_status()
        client.headers['Authorization']='Bearer '+login.json()['access_token']
        response=client.get('/settings'); response.raise_for_status()
        config=response.json()
        assert not config['uploads_enabled'], 'Uploads must stay disabled'
        report['configuration']=config['active_configuration']
        print(json.dumps(report),flush=True)
        personalities=client.get('/personalities').json()
        channels=client.get('/channels').json()
        persona=next(p for p in personalities if p['name']=='Cristiano Ronaldo' and p['enabled'])
        channel=next(c for c in channels if not persona['channel_id'] or c['id']==persona['channel_id'])
        response=client.post('/videos/generate',json={'channel_id':channel['id'],'personality_id':persona['id'],
                             'topic_mode':'current','duration':30,'voice_style':'auto'})
        response.raise_for_status()
        job=response.json()
        report['job_id']=job['id']
        report['new_current_topic_job']=True
        last=None
        for _ in range(300):
            response=client.get('/videos/'+job['id']);response.raise_for_status();job=response.json()
            if job['current_step']!=last:
                print(json.dumps({'job_id':job['id'],'step':job['current_step']}),flush=True)
                last=job['current_step']
            if job['status'] not in {'researching','script_generation','collecting_assets','voice_generation','rendering','creating_cover'}:
                break
            time.sleep(2)
        report.update(status=job['status'],current_step=job['current_step'],error=job['error_message'],
                      retryable=job['retryable'],sources=job['sources'],evidence=job['evidence'],
                      script_provider=job['script_provider'],script=job['script'],warnings=job['warnings'],
                      verification_status=job['verification_status'],uploads_enabled=False)
        report['demo_fallback_used']=bool(job['script_provider'] and 'development' in job['script_provider'].lower())
        if job['status']=='verification_required':
            from app.database.session import SessionLocal
            from app.models import ResearchCandidate, VideoJob
            with SessionLocal() as db:
                saved=db.get(VideoJob,job['id'])
                candidates=db.query(ResearchCandidate).filter(
                    ResearchCandidate.channel_id==channel['id'],ResearchCandidate.personality_id==persona['id'],
                    ResearchCandidate.created_at>=saved.created_at).all()
                report['candidate_sources']=[{'title':row.title,'status':row.status,'reason':row.rejection_reason,
                    **{key:json.loads(row.data).get(key) for key in ('source_name','source_url','published_at')}} for row in candidates]
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in {'script','evidence'}},indent=2),flush=True)


if __name__=='__main__':
    main()
