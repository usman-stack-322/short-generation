"""Select only installed/API-advertised voices compatible with the requested language."""
import json
import re
import subprocess
import sys
from dataclasses import dataclass
import httpx
from app.core.config import settings
from app.core.languages import language_info


class NarrationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Narrator:
    provider: str
    voice: str
    locale: str
    reason: str = ''


def google_headers():
    if settings.google_tts_api_key:
        return {'x-goog-api-key':settings.google_tts_api_key}
    import google.auth
    from google.auth.transport.requests import Request
    scopes=['https://www.googleapis.com/auth/cloud-platform']
    credentials,_=(google.auth.load_credentials_from_file(settings.google_application_credentials,scopes=scopes)
                   if settings.google_application_credentials else google.auth.default(scopes=scopes))
    credentials.refresh(Request())
    return {'Authorization':'Bearer '+credentials.token}


def configured(provider):
    from pathlib import Path
    if provider=='kokoro_onnx':return (Path(__file__).resolve().parents[3]/'generated/hybrid-review/models/verified-int8.json').is_file()
    return (provider=='local' or provider=='google' and bool(settings.google_tts_api_key or settings.google_application_credentials)
            or provider=='elevenlabs' and bool(settings.elevenlabs_api_key))


def local_voices():
    response=subprocess.run([sys.executable,'-m','app.tts.local_worker','--list'],capture_output=True,
                            text=True,encoding='utf-8',check=True,timeout=20)
    return json.loads(response.stdout)


def resolve_narrator(provider, code, preferred=''):
    language=language_info(code)
    if not configured(provider):
        raise NarrationUnavailable(f'{provider} is not configured')
    if provider=='kokoro_onnx':
        if language.code.split('-')[0]!='en':raise NarrationUnavailable('Reviewed Kokoro supports English only')
        if preferred not in {'bm_george','bf_emma','am_michael'}:raise NarrationUnavailable('Select an explicit reviewed generic Kokoro preset')
        return Narrator(provider,preferred,'en-GB' if preferred.startswith('b') else 'en-US','Explicit reviewed local Kokoro preset')
    if provider=='local':
        matches=[]
        for voice in local_voices():
            metadata=' '.join([voice['name'],*voice.get('languages',[]),voice['id']]).casefold().replace('_','-')
            if any(re.search(r'(?<![a-z])'+re.escape(alias)+r'(?![a-z])',metadata) for alias in language.local_aliases):
                matches.append(voice)
        exact=next((v for v in matches if preferred in (v['id'],v['name'])),None)
        if not matches:
            raise NarrationUnavailable(f'Local narrator does not support {language.name}. Install a compatible system voice or configure Google/ElevenLabs.')
        if preferred and re.fullmatch(r'[a-z]{2}-[A-Z]{2}',preferred) and preferred.split('-')[0]!=language.code.split('-')[0]:
            raise NarrationUnavailable(f'The requested narrator locale is incompatible with {language.name}')
        return Narrator(provider,(exact or matches[0])['name'],language.code,'Installed compatible system narrator')
    if provider=='google':
        response=httpx.get('https://texttospeech.googleapis.com/v1/voices',headers=google_headers(),timeout=30)
        response.raise_for_status()
        locales=language.google_locales or (language.code,)
        matches=[v for v in response.json().get('voices',[]) if any(loc in v.get('languageCodes',[]) for loc in locales)]
        requested=preferred if preferred.count('-')>=3 else ''
        if requested and not any(v['name']==requested for v in matches):
            raise NarrationUnavailable(f'The requested Google narrator is incompatible with {language.name}')
        default=requested or settings.google_tts_voice
        matches.sort(key=lambda v:(v['name']!=default,not any(k in v['name'] for k in ('Standard-','Wavenet-','Neural2-')),v['name']))
        if not matches: raise NarrationUnavailable(f'Google advertises no compatible {language.name} voice')
        voice=matches[0]
        locale=next(loc for loc in locales if loc in voice['languageCodes'])
        return Narrator(provider,voice['name'],locale,'Google voices.list confirmed language compatibility')
    if provider=='elevenlabs':
        response=httpx.get('https://api.elevenlabs.io/v1/models',headers={'xi-api-key':settings.elevenlabs_api_key},timeout=30)
        response.raise_for_status()
        model=next((m for m in response.json() if m['model_id']=='eleven_multilingual_v2'),{})
        if not model.get('can_do_text_to_speech') or language.code.split('-')[0] not in {l['language_id'] for l in model.get('languages',[])}:
            raise NarrationUnavailable(f'The configured ElevenLabs model does not support {language.name}')
        allowed=[v.strip() for v in settings.elevenlabs_allowed_voice_ids.split(',') if v.strip()]
        selected=preferred if preferred in allowed else settings.elevenlabs_voice_id
        if not selected or selected not in allowed:
            raise NarrationUnavailable('Configure an allowlisted generic ElevenLabs narrator')
        return Narrator(provider,selected,language.code,'ElevenLabs model metadata confirmed language compatibility')
    raise NarrationUnavailable('Unknown narration provider')
