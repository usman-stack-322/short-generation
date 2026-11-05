"""Supervised normal-API generation; persists progress without credentials."""
import json,time,httpx
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'generated/fresh-pilots.json'
refs=[
 'https://www.skysports.com/football/news/4575921/ronaldo-wins-ballon-dor',
 'https://www.theguardian.com/football/2008/dec/02/ronaldo-manchesterunited',
 'https://www.uefa.com/uefachampionsleague/news/0254-0d7c88baed8d-31759f0c45c3-1000--messi-wins-2009-ballon-d-or/',
 'https://www.theguardian.com/football/2004/apr/26/newsstory.sport5',
 'https://www.uefa.com/news-media/news/019c-0f8e9d0ccd0c-19183188d315-1000--henry-honoured-by-peers/',
 'https://www.theguardian.com/football/2014/dec/16/thierry-henry-retires-arsenal-barcelona-france-fact-file-career']
with httpx.Client(base_url='http://127.0.0.1:8000/api',timeout=30) as c:
 a=c.post('/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});a.raise_for_status()
 c.headers['Authorization']='Bearer '+a.json()['access_token']
 assert c.get('/settings').json()['uploads_enabled'] is False
 channel='7c6a91c7-1b7e-4d27-9fb7-cee30b1a8e37'
 r=c.patch('/channels/'+channel,json={'evergreen_source_urls':refs,'automatic_evergreen_fallback':True,'automatic_generation_enabled':False});r.raise_for_status()
 people={p['name']:p for p in c.get('/personalities').json() if p['channel_id']==channel}
 result=[]
 for name in ['Cristiano Ronaldo','Lionel Messi','Thierry Henry']:
  r=c.post('/videos/generate',json={'channel_id':channel,'personality_id':people[name]['id'],'duration':30,'language':'en-US','tts_provider':'local','operation_id':'fresh-supervised-'+str(uuid4())});r.raise_for_status()
  result.append({'subject':name,'job_id':r.json()['id']});OUT.write_text(json.dumps(result,indent=2));print(result[-1],flush=True)
 deadline=time.monotonic()+2400
 while time.monotonic()<deadline:
  for row in result:
   r=c.get('/videos/'+row['job_id']);r.raise_for_status();row['job']=r.json()
  OUT.write_text(json.dumps(result,indent=2))
  states=[r['job']['status'] for r in result];print(states,flush=True)
  if all(s not in ['researching','script_generation','collecting_assets','voice_generation','rendering','creating_cover'] for s in states):break
  time.sleep(10)
