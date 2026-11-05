"""Credential-aware real RSS acceptance probe. Never uploads or fabricates verification."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import WorkspaceSettings


def main():
    settings.youtube_uploads_enabled=False
    settings.rss_feeds += ',https://news.google.com/rss/search?q=Cristiano%20Ronaldo%20when%3A3d&hl=en-US&gl=US&ceid=US%3Aen'
    with TestClient(app) as client:
        auth=client.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'}).json()
        headers={'Authorization':'Bearer '+auth['access_token']}
        workspace_id=auth['workspace_id']
        assert client.get('/api/dashboard',headers=headers).status_code==200
        channel=client.post('/api/channels',headers=headers,json={'name':'Day 2 Ronaldo Research Test'}).json()
        persona=client.post('/api/personalities',headers=headers,json={'name':'Cristiano Ronaldo','category':'Football',
                'channel_id':channel['id'],'keywords':['Cristiano Ronaldo','CR7'],'research_keywords':['Cristiano Ronaldo','Ronaldo']}).json()
        with SessionLocal() as db:
            record=db.get(WorkspaceSettings,workspace_id)
            previous=record.data if record else None
        prefs=client.get('/api/settings',headers=headers).json()['preferences']
        client.put('/api/settings',headers=headers,json={**prefs,'research_provider':'rss'})
        try:
            sources=client.post('/api/research/candidates',headers=headers,json={'channel_id':channel['id'],'personality_id':persona['id']})
            rows=sources.json() if sources.status_code==200 else []
            selected=next((row for row in rows if row['status']=='verified'),None)
            payload={'channel_id':channel['id'],'personality_id':persona['id'],'duration':30,'topic_mode':'current'}
            if selected: payload['candidate_id']=selected['id']
            generated=client.post('/api/videos/generate',headers=headers,json=payload)
            assert generated.status_code==201,generated.text
            job=client.get('/api/videos/'+generated.json()['id'],headers=headers).json()
            blocked=client.post('/api/videos/'+job['id']+'/upload',headers=headers,
                        json={'confirmed':True,'privacy_status':'private','made_for_kids':False})
            assert blocked.status_code==409
            report={'full_live_e2e_complete':False,'real_upload_performed':False,'job_id':job['id'],
                    'channel_type':'manual test channel; not OAuth connected','oauth':'not configured',
                    'gemini':'configured but live verification still required' if settings.gemini_api_key else 'not configured',
                    'research_http_status':sources.status_code,'candidate_count':len(rows),
                    'verified_count':sum(row['status']=='verified' for row in rows),
                    'held_count':sum(row['status']=='verification_required' for row in rows),
                    'rejected_count':sum(row['status']=='rejected' for row in rows),
                    'pipeline_status':job['status'],'error':job['error_message'],'upload_without_approval_http_status':blocked.status_code,
                    'browser_review':'unavailable: no browser connected',
                    'limitations':['No Google OAuth/Gemini credentials supplied','Sensitive or singly sourced current stories are held, not invented',
                                   'Wikimedia live probe encountered DNS failure; licensed adapter fallback is original illustrations'],
                    'sources':[{'title':row['title'],'source':row['source_name'],'url':row['source_url'],
                                'published_at':row['published_at'],'status':row['status'],'reason':row['rejection_reason']} for row in rows]}
            if job['status']=='verification_required':
                assert job['script'] is None,'Unverified factual news must not generate a script'
            output=Path(settings.generated_dir).resolve()/'day2-acceptance-report.json'
            output.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps({key:value for key,value in report.items() if key!='sources'},indent=2))
        finally:
            with SessionLocal() as db:
                record=db.get(WorkspaceSettings,workspace_id)
                if record:
                    record.data=previous or '{}'
                    db.commit()


if __name__=='__main__':
    main()
