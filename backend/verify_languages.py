"""Live script/SEO samples, real font/subtitle checks and honest narrator availability."""
import json
import re
from pathlib import Path
from PIL import Image
from app.core.config import settings
from app.core.languages import language_info
from app.ai.scripts import generate_script,generate_seo
from app.ai.reliability import safe_detail
from app.tts.capabilities import configured,resolve_narrator
from app.video.subtitles import write_subtitles
from app.video.cover import create_cover


def main(codes=('en-US','ur-PK','es-ES','it-IT','zh-CN'),target_model=None):
    assert settings.gemini_api_key.strip() and not settings.youtube_uploads_enabled
    root=Path(settings.generated_dir)/'language-acceptance'
    root.mkdir(exist_ok=True)
    background=root/'background.png'
    Image.new('RGB',(1080,1920),'#18304b').save(background)
    configured_primary=settings.gemini_model
    if target_model:
        assert target_model==settings.gemini_fallback_model, 'Only the already configured fallback may be targeted'
        settings.gemini_model=target_model  # Diagnostic process only; never writes configuration.
    previous=root/'report.json'
    report=[r for r in json.loads(previous.read_text(encoding='utf-8')) if r['language'] not in codes] if previous.exists() else []
    for code in codes:
        print(json.dumps({'language':code,'step':'live_script_and_seo'}),flush=True)
        result={'language':code,'name':language_info(code).name,'demo_fallback_used':False,
                'configured_primary':configured_primary,'diagnostic_target_model':target_model}
        try:
            script,provider=generate_script('Cristiano Ronaldo: historical career achievements','Cristiano Ronaldo','Professional',30,code,
                'Historical facts only: As of 2017 Cristiano Ronaldo had won 5 Ballon d\u2019Or awards. '
                'Portugal won UEFA EURO 2016 with Ronaldo as captain. Include ASCII numerals 5 and 2016 in the spoken script. '
                'No other numeric claims, no current-news claims, no emojis. Preserve the proper names appropriately.')
            seo=generate_seo('Cristiano Ronaldo: historical career achievements','Cristiano Ronaldo',script,code)
            numbers=set(re.findall(r'\d+',script['full_script']))
            result.update(script=script,seo=seo,provider=provider,script_numeric_values=sorted(numbers),
                          factual_values_preserved={'5','2016'}.issubset(numbers),
                          numeric_values_unchanged=numbers.issubset({'5','2016','2017'}))
            if code in ('ur-PK','zh-CN'):
                pattern=r'[\u0600-\u06ff]' if code=='ur-PK' else r'[\u3400-\u9fff]'
                assert re.search(pattern,script['full_script']) and re.search(pattern,seo['cover_text'])
            destination=root/code
            destination.mkdir(exist_ok=True)
            write_subtitles(script['full_script'],29.4,destination/'captions.ass',destination/'captions.srt',{'language':code})
            create_cover(background,seo['cover_text'],destination/'cover.png',language=code)
            result.update(structured_script_valid=True,subtitles='Passed; generated from final narration',cover='Passed')
            voices=[]
            errors=[]
            for name in ('local','google','elevenlabs'):
                if not configured(name):continue
                try:
                    voice=resolve_narrator(name,code)
                    voices.append({'provider':voice.provider,'voice':voice.voice,'locale':voice.locale})
                    break
                except Exception as exc:
                    errors.append(f'{name}: {type(exc).__name__}')
            result['compatible_narrator']=voices[0] if voices else None
            result['narrator_status']='Available' if voices else 'Unavailable; configure a compatible narrator'
            result['status']='Passed'
        except Exception as exc:
            result.update(status='Failed',error=safe_detail(exc),error_type=type(exc).__name__)
        report.append(result)
        (root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in {'script','seo'}},ensure_ascii=True),flush=True)
    settings.gemini_model=configured_primary


if __name__=='__main__':main()
