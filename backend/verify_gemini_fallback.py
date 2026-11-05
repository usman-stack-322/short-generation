"""Explicit single-call fallback probes; no retries or demo generation."""
import json
import re
from pathlib import Path

import httpx

from app.ai.reliability import safe_detail
from app.ai.scripts import FIELDS, GeminiProvider
from app.core.config import settings

MODEL = 'gemini-3.5-flash-lite'
assert settings.gemini_api_key.strip(), 'Gemini key missing'
assert not settings.youtube_uploads_enabled, 'Uploads must remain disabled'
report = {'primary_model': settings.gemini_model, 'primary_result': 'Previous live operation: HTTP 503 on three attempts',
          'fallback_model': MODEL, 'fallback_attempts': 0, 'probe': 'Not run', 'script': 'Not run',
          'structured_json_valid': False, 'demo_fallback_used': False, 'youtube_uploads_enabled': False}
try:
    with httpx.Client(timeout=45, headers={'x-goog-api-key': settings.gemini_api_key}) as client:
        metadata = client.get(f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}')
        metadata.raise_for_status()
        assert 'generateContent' in metadata.json().get('supportedGenerationMethods', [])
        report['metadata_confirmed'] = True
        report['fallback_attempts'] += 1
        response = client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent',
                               json={'contents': [{'parts': [{'text': 'Return only valid JSON: {"status":"ok"}'}]}],
                                     'generationConfig': {'responseMimeType': 'application/json'}})
        response.raise_for_status()
        payload = response.json()
        text = ''.join(p.get('text', '') for p in payload['candidates'][0]['content']['parts'] if not p.get('thought'))
        assert json.loads(text) == {'status': 'ok'}, 'Tiny JSON probe validation failed'
        report['probe'] = 'Passed'
    # Only configure a fallback which has passed an actual JSON generation request.
    env_path = Path(__file__).resolve().parent / '.env'
    env = env_path.read_text(encoding='utf-8')
    replacement = f'GEMINI_FALLBACK_MODEL={MODEL}'
    updated = re.sub(r'^GEMINI_FALLBACK_MODEL=.*$', replacement, env, flags=re.MULTILINE)
    if updated == env and not re.search(r'^GEMINI_FALLBACK_MODEL=', env, re.MULTILINE):
        updated = env.rstrip() + '\n' + replacement + '\n'
    env_path.write_text(updated, encoding='utf-8')
    report['fallback_configured'] = True
    prompt = ('Write an original English 30-second YouTube Shorts script, approximately 65-75 spoken words, '
              'about Cristiano Ronaldo career achievements. Only well-established historical facts, no current '
              'totals or disputed claims. Return JSON with nonempty hook, context, main_story, why_it_matters, '
              'ending, full_script (combining the five sections), visual_keywords (list of strings), '
              'scenes (6-12 objects with visual_query and narration). Use generic reusable football visuals.')
    report['fallback_attempts'] += 1
    output = GeminiProvider()._request(prompt, model=MODEL)
    assert all(isinstance(output.get(k), str) and output[k].strip() for k in (*FIELDS, 'full_script'))
    report.update(script='Passed', structured_json_valid=True, scene_count=len(output['scene_suggestions']),
                  word_count=len(output['full_script'].split()), generated_script=output)
except httpx.HTTPStatusError as exc:
    report.update(http_status=exc.response.status_code, error=safe_detail(exc.response.text))
except Exception as exc:
    report.update(error_type=type(exc).__name__, error=safe_detail(exc))
finally:
    path = Path(settings.generated_dir).resolve() / 'gemini-fallback-verification.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'generated_script'}, indent=2))
