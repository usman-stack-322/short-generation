"""Normal local API pilot. No fixture DB, provider mocks, approval or uploading."""
import json
import sys
from pathlib import Path
from uuid import uuid4
import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'generated'/'implementation-pilot.json'

def main():
    with httpx.Client(base_url='http://127.0.0.1:8000/api', timeout=600) as c:
        auth = c.post('/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'})
        auth.raise_for_status()
        c.headers['Authorization'] = 'Bearer '+auth.json()['access_token']
        config=c.get('/settings').json()['active_configuration']
        assert not config.get('youtube_uploads_enabled'), 'Uploads must remain disabled'
        result={'configuration':{k:config.get(k) for k in ('gemini_configured','research_provider','asset_provider','youtube_uploads_enabled')},'attempts':[]}
        channel=c.post('/channels',json={'name':'Supervised Pilot October 2026','automatic_evergreen_fallback':True,'automatic_generation_enabled':False,'tts_provider':'local','niche':'Football history','default_language':'en-US'})
        channel.raise_for_status(); channel=channel.json()
        for name in ('Cristiano Ronaldo','Lionel Messi','Thierry Henry'):
            person=c.post('/personalities',json={'name':name,'category':'Football','channel_id':channel['id'],'research_keywords':[name]})
            person.raise_for_status();person=person.json()
            entry={'subject':name,'channel_id':channel['id'],'personality_id':person['id']}
            result['attempts'].append(entry);OUT.write_text(json.dumps(result,indent=2))
            try:
                r=c.post('/videos/generate',json={'channel_id':channel['id'],'personality_id':person['id'],'duration':30,'language':'en-US','tts_provider':'local','operation_id':'pilot-'+str(uuid4())})
                r.raise_for_status();job=r.json()
                entry.update(job_id=job['id'],review_url='http://127.0.0.1:5173/videos/'+job['id'])
                # Background generation may continue after the HTTP response.
                current=c.get('/videos/'+job['id']);current.raise_for_status()
                entry.update(status=current.json()['status'],error=current.json().get('error_message'))
            except Exception as exc:
                entry['error']=type(exc).__name__+': '+str(exc)
            OUT.write_text(json.dumps(result,indent=2))
            print(json.dumps(entry),flush=True)

if __name__=='__main__':main()
