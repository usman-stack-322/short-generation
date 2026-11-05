"""One live, fallback-free probe through the existing Gemini provider."""
import json
from pathlib import Path
import httpx
from app.core.config import settings
from app.ai.scripts import GeminiProvider, FIELDS

report={'gemini_configured':bool(settings.gemini_api_key.strip()),'model':settings.gemini_model,
        'live_api_request':'Failed','fallback_used':False,'request_count':0,'topic':'Cristiano Ronaldo career achievements',
        'requested_duration_seconds':30,'uploads_enabled':settings.youtube_uploads_enabled}
assert not settings.youtube_uploads_enabled,'Uploads must remain disabled'
original_post=httpx.post
captured={}
def tracked_post(*args,**kwargs):
    report['request_count']+=1
    response=original_post(*args,**kwargs)
    captured['response']=response
    return response
httpx.post=tracked_post
prompt=('Write an original English YouTube Shorts script lasting approximately 30 seconds, about 65–75 spoken words. '
        'Harmless manual topic: Cristiano Ronaldo career achievements. Use only well-established historical facts; '
        'avoid changing current totals, rumors, recent news, and unsupported claims. Short natural spoken sentences. '
        'Return only JSON containing nonempty strings hook, context, main_story, why_it_matters, ending, full_script. '
        'full_script must combine those five sections. Include visual_keywords as a list of strings and scenes as '
        '6–12 objects, each with visual_query and narration. Plan reusable generic football imagery; no voice cloning.')
try:
    if not report['gemini_configured']:
        raise RuntimeError('GEMINI_API_KEY was not detected in backend/.env')
    result=GeminiProvider()._request(prompt)
    response=captured['response']
    raw=json.loads(response.json()['candidates'][0]['content']['parts'][0]['text'])
    required=(*FIELDS,'full_script')
    report['http_status']=response.status_code
    report['model_recognized_by_api']=True
    report['structured_fields']={key:isinstance(raw.get(key),str) and bool(raw[key].strip()) for key in required}
    assert all(report['structured_fields'].values()),'Required structured output field missing/empty'
    report['full_script_matches_sections']=' '.join(raw['full_script'].split())==' '.join(' '.join(raw[key].strip() for key in FIELDS).split())
    assert report['full_script_matches_sections'],'Model full_script differs from the five section strings'
    report['scene_count']=len(result['scene_suggestions'])
    report['scene_plan_valid']=6<=report['scene_count']<=12 and all(isinstance(s.get('narration'),str) and s['narration'].strip() and s.get('visual_query') for s in result['scene_suggestions'])
    assert report['scene_plan_valid'],'Scene plan invalid'
    report['word_count']=len(raw['full_script'].split())
    report['live_api_request']='Passed'
    report['script']=raw
except httpx.HTTPStatusError as exc:
    report['http_status']=exc.response.status_code
    try: report['api_error']=exc.response.json().get('error',exc.response.json())
    except ValueError: report['api_error']=exc.response.text[:3000]
except Exception as exc:
    report['error_type']=type(exc).__name__
    report['error']=str(exc)
    if 'response' in captured: report['http_status']=captured['response'].status_code
finally:
    httpx.post=original_post
    safe=json.dumps(report,indent=2,ensure_ascii=True)
    if settings.gemini_api_key:
        safe=safe.replace(settings.gemini_api_key,'[REDACTED]')
    path=Path(settings.generated_dir).resolve()/'gemini-live-verification.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(safe,encoding='utf-8')
    summary=json.loads(safe)
    summary.pop('script',None)
    print(json.dumps(summary,indent=2))
