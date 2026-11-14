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
    if provider=='gemini_tts':
        from app.ai.smart_router import parse_gemini_keys
        return bool(parse_gemini_keys())
    return (provider=='local' or provider=='google' and bool(settings.google_tts_api_key or settings.google_application_credentials)
            or provider=='elevenlabs' and bool(settings.elevenlabs_api_key))


def local_voices():
    from pathlib import Path
    response=subprocess.run(
        [sys.executable,'-m','app.tts.local_worker','--list'],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,text=True,encoding='utf-8',check=True,timeout=20,
    )
    return json.loads(response.stdout)


GEMINI_STUDIO_VOICES={
    'Charon':'Charon (Informative Male — Newscaster)',
    'Orus':'Orus (Firm Male)',
    'Kore':'Kore (Firm Female — Newscaster)',
    'Fenrir':'Fenrir (Excitable Male)',
    'Puck':'Puck (Upbeat Male)',
    'Aoede':'Aoede (Breezy Female)',
    'Zephyr':'Zephyr (Bright Female)',
    'Leda':'Leda (Youthful Female)',
    'Rasalgethi':'Rasalgethi (Informative Male)',
    'Alnilam':'Alnilam (Firm Male)',
    'Iapetus':'Iapetus (Clear Male)',
    'Erinome':'Erinome (Clear Female)',
    'Enceladus':'Enceladus (Breathy Male)',
    'Umbriel':'Umbriel (Easy-going Male)',
    'Algieba':'Algieba (Smooth Male)',
    'Despina':'Despina (Smooth Female)',
    'Algenib':'Algenib (Gravelly Male)',
    'Laomedeia':'Laomedeia (Upbeat Female)',
    'Achernar':'Achernar (Soft Female)',
    'Schedar':'Schedar (Even Male)',
    'Gacrux':'Gacrux (Mature Female)',
    'Pulcherrima':'Pulcherrima (Forward Female)',
    'Achird':'Achird (Friendly Male)',
    'Zubenelgenubi':'Zubenelgenubi (Casual Male)',
    'Vindemiatrix':'Vindemiatrix (Gentle Female)',
    'Sadachbia':'Sadachbia (Lively Male)',
    'Sadaltager':'Sadaltager (Knowledgeable Male)',
    'Sulafat':'Sulafat (Warm Female)',
    'Callirrhoe':'Callirrhoe (Easy-going Female)',
    'Autonoe':'Autonoe (Bright Female)',
}

GEMINI_STYLE_OPTIONS=[
    'Newscaster',
    'Documentary',
    'Storyteller',
    'Sports Hype',
    'Conversational',
    'Dramatic',
    'Calm & Serious',
]

GEMINI_PACE_OPTIONS=[
    'Rapid',
    'Fast',
    'Normal',
    'Measured',
]

GEMINI_ACCENT_OPTIONS=[
    'American English',
    'British English',
    'Australian English',
    'Canadian English',
    'Indian English',
    'Neutral',
]


KOKORO_ENGLISH_VOICES={
    'af_alloy':'Alloy (American Female)','af_aoede':'Aoede (American Female)','af_bella':'Bella (American Female)',
    'af_heart':'Heart (American Female)','af_jessica':'Jessica (American Female)','af_kore':'Kore (American Female)',
    'af_nicole':'Nicole (American Female)','af_nova':'Nova (American Female)','af_river':'River (American Female)',
    'af_sarah':'Sarah (American Female)','af_sky':'Sky (American Female)',
    'am_adam':'Adam (American Male)','am_echo':'Echo (American Male)','am_eric':'Eric (American Male)',
    'am_fenrir':'Fenrir (American Male)','am_liam':'Liam (American Male)','am_michael':'Michael (American Male)',
    'am_onyx':'Onyx (American Male)','am_puck':'Puck (American Male)','am_santa':'Santa (American Male)',
    'bf_alice':'Alice (British Female)','bf_emma':'Emma (British Female)','bf_isabella':'Isabella (British Female)',
    'bf_lily':'Lily (British Female)',
    'bm_daniel':'Daniel (British Male)','bm_fable':'Fable (British Male)','bm_george':'George (British Male)',
    'bm_lewis':'Lewis (British Male)',
}


def list_voice_options():
    options=[]
    if configured('gemini_tts'):
        for vid,label in GEMINI_STUDIO_VOICES.items():
            options.append({'provider':'gemini_tts','voice':vid,'label':label})
    if configured('kokoro_onnx'):
        for vid,label in KOKORO_ENGLISH_VOICES.items():
            options.append({'provider':'kokoro_onnx','voice':vid,'label':label,'language':'English','accent':'en-GB' if vid.startswith('b') else 'en-US'})
    try:
        for v in local_voices():
            options.append({'provider':'local','voice':v['name'],'label':v['name']+' (System)','languages':v.get('languages',[])})
    except Exception:
        pass
    if configured('elevenlabs'):
        allowed=[v.strip() for v in settings.elevenlabs_allowed_voice_ids.split(',') if v.strip()]
        if settings.elevenlabs_voice_id and settings.elevenlabs_voice_id not in allowed:
            allowed.insert(0,settings.elevenlabs_voice_id)
        for vid in allowed:
            options.append({'provider':'elevenlabs','voice':vid,'label':'ElevenLabs ('+vid[:8]+')'})
    return options


def resolve_narrator(provider, code, preferred=''):
    language=language_info(code)
    if not configured(provider):
        raise NarrationUnavailable(f'{provider} is not configured')
    if provider=='gemini_tts':
        voice=preferred if preferred in GEMINI_STUDIO_VOICES else 'Charon'
        return Narrator(provider,voice,language.code,'Google AI Studio Gemini Speech Generation')
    if provider=='kokoro_onnx':
        if language.code.split('-')[0]!='en':raise NarrationUnavailable('Reviewed Kokoro supports English only')
        if preferred not in KOKORO_ENGLISH_VOICES:raise NarrationUnavailable('Select an explicit reviewed generic Kokoro preset')
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
