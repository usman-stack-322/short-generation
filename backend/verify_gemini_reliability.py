"""One live generation operation through the existing bounded Gemini policy."""
import json
from pathlib import Path
from app.core.config import settings
from app.ai.scripts import GeminiProvider,FIELDS
from app.ai.reliability import GeminiGenerationError

assert settings.gemini_api_key.strip(),'GEMINI_API_KEY is not configured'
assert not settings.youtube_uploads_enabled,'YouTube uploads must remain disabled'
provider=GeminiProvider()
report={'gemini_configured':True,'primary_model':settings.gemini_model,'final_status':'Failed',
        'structured_json_validated':False,'demo_fallback_used':False,'youtube_uploads_enabled':False,
        'topic':'Cristiano Ronaldo career achievements','duration_seconds':30}
prompt=('Write an original English 30-second YouTube Shorts script, approximately 65–75 spoken words, '
        'on the harmless manual topic Cristiano Ronaldo career achievements. Use only well-established historical '
        'facts, not current totals or disputed claims. Return only JSON with nonempty string fields hook, context, '
        'main_story, why_it_matters, ending, full_script. full_script must combine the five sections. '
        'Also return visual_keywords (list of strings), and scenes (6–12 objects with visual_query and narration). '
        'Suggest reusable generic football visuals and a generic narrator; no voice cloning.')
try:
    output=provider.generate(prompt)
    assert all(isinstance(output.get(field),str) and output[field].strip() for field in (*FIELDS,'full_script'))
    assert 6<=len(output['scene_suggestions'])<=12
    report.update(final_status='Passed',structured_json_validated=True,scene_count=len(output['scene_suggestions']),
                  word_count=len(output['full_script'].split()),script=output)
except GeminiGenerationError as exc:
    report.update(error=str(exc),retryable=exc.retryable)
except Exception as exc:
    report.update(error_type=type(exc).__name__,error='Live structured-output validation failed; inspect the backend verification.')
finally:
    policy=provider.retry_policy
    report.update(attempts=policy.attempts,model_used=policy.model_used,fallback_model_used=policy.fallback_used,
                  fallback_model_configured=bool(settings.gemini_fallback_model.strip()))
    safe=json.dumps(report,indent=2,ensure_ascii=True).replace(settings.gemini_api_key,'[REDACTED]')
    path=Path(settings.generated_dir).resolve()/'gemini-reliability-verification.json'
    path.write_text(safe,encoding='utf-8')
    summary=json.loads(safe);summary.pop('script',None)
    print(json.dumps(summary,indent=2))
