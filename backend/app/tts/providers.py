"""Narrator providers. Celebrity voice cloning is deliberately unsupported."""
import json
import logging
import subprocess
import sys
import wave
import base64
import httpx
from pathlib import Path
from typing import Protocol
from app.core.config import settings
from app.tts.director import VoiceProfile
from app.tts.delivery import provider_controls, prepare_delivery, google_ssml
from app.tts.capabilities import resolve_narrator, configured, NarrationUnavailable

logger = logging.getLogger(__name__)

class TTSProvider(Protocol):
    def generate_voice(self, text: str, voice: str, output_path: Path, speed: float=1, profile=None, segments=None) -> str: ...

class LocalTTSProvider:
    name = "Local narrator (pyttsx3)"

    def generate_voice(self, text, voice, output_path, speed=1, profile=None, segments=None):
        controls = provider_controls('local', profile or VoiceProfile(), speed)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Isolate SAPI and enforce a timeout: a broken speech driver cannot hang the worker.
            subprocess.run([sys.executable, '-m', 'app.tts.local_worker',
                            str(output_path), voice, str(controls['speed']), str(controls['volume'])], input=text, encoding='utf-8',
                           capture_output=True, check=True, timeout=75)
            with wave.open(str(output_path), 'rb') as audio:
                pcm=audio.readframes(audio.getnframes())
                if audio.getnframes() < 100 or not any(pcm):
                    raise RuntimeError('Speech engine wrote empty audio')
            if sys.platform=='win32':
                from app.video.alignment import load_boundaries
                if not load_boundaries(output_path,text):
                    raise NarrationUnavailable('Local narration word boundaries are incomplete or invalid')
            return 'Local narrator (Windows SAPI)' if output_path.with_suffix('.words.json').is_file() else self.name
        except Exception as exc:
            raise NarrationUnavailable('Local speech engine failed; no silent output is accepted') from exc

class GoogleTTSProvider:
    def generate_voice(self, text, voice, output_path, speed=1, profile=None, segments=None):
        profile = VoiceProfile.model_validate(profile or VoiceProfile())
        headers = {}
        if settings.google_tts_api_key:
            headers['x-goog-api-key'] = settings.google_tts_api_key
        else:
            import google.auth
            from google.auth.transport.requests import Request
            scopes=['https://www.googleapis.com/auth/cloud-platform']
            credentials,_=(google.auth.load_credentials_from_file(settings.google_application_credentials,scopes=scopes)
                           if settings.google_application_credentials else google.auth.default(scopes=scopes))
            credentials.refresh(Request())
            headers['Authorization'] = 'Bearer ' + credentials.token
        language = '-'.join(voice.split('-')[:2])
        selected_voice={'languageCode':language}
        if voice.count('-') >= 3:
            selected_voice['name'] = voice
        elif settings.google_tts_voice.startswith(language):
            selected_voice['name']=settings.google_tts_voice
        controls = provider_controls('google', profile, speed, selected_voice.get('name',''))
        narration = {'ssml': google_ssml(segments or prepare_delivery(text, profile), profile)} if controls else {'text':text}
        response = httpx.post('https://texttospeech.googleapis.com/v1/text:synthesize', headers=headers,
            json={'input':narration, 'voice':selected_voice,
                  'audioConfig':{'audioEncoding':'LINEAR16', **controls}}, timeout=60)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True,exist_ok=True)
        output_path.write_bytes(base64.b64decode(response.json()['audioContent'],validate=True))
        return 'Google TTS narrator'

class ElevenLabsProvider:
    def generate_voice(self, text, voice, output_path, speed=1, profile=None, segments=None):
        allowed = [v.strip() for v in settings.elevenlabs_allowed_voice_ids.split(',') if v.strip()]
        voice_id = voice if voice in allowed else settings.elevenlabs_voice_id
        if not settings.elevenlabs_api_key or not voice_id or voice_id not in allowed:
            raise RuntimeError('Configure an allowed generic narrator voice ID; cloned/celebrity voices are unsupported')
        response = httpx.post(f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps',
            headers={'xi-api-key':settings.elevenlabs_api_key}, params={'output_format':'mp3_44100_128'},
            json={'text':text,'model_id':'eleven_multilingual_v2',
                  'voice_settings':{**provider_controls('elevenlabs',profile or VoiceProfile(),speed),'use_speaker_boost':True}},timeout=90)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True,exist_ok=True)
        temporary = output_path.with_suffix('.mp3')
        response_data=response.json()
        temporary.write_bytes(base64.b64decode(response_data['audio_base64'],validate=True))
        try:
            subprocess.run([settings.ffmpeg_path,'-y','-loglevel','error','-i',str(temporary),str(output_path)],
                           check=True,capture_output=True,timeout=60)
        finally:
            temporary.unlink(missing_ok=True)
        from app.video.alignment import write_character_boundaries
        write_character_boundaries(output_path,text,response_data.get('alignment') or {},'ElevenLabs original character alignment - eleven_multilingual_v2')
        return 'ElevenLabs allowed narrator'

import threading

_KOKORO_LOCK = threading.Lock()
_KOKORO_WORKERS = {}


class KokoroTTSProvider:
    """Explicit local provider with warm persistent worker; no cloud or narrator fallback."""
    @staticmethod
    def _ensure_worker(python: Path, runtime: Path):
        key = (str(python), str(runtime))
        proc = _KOKORO_WORKERS.get(key)
        if proc is not None and proc.poll() is None:
            return proc
        backend_dir = str(Path(__file__).resolve().parents[2])
        proc = subprocess.Popen(
            [str(python), '-m', 'app.tts.kokoro_worker', '--serve', str(runtime)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding='utf8', bufsize=1, cwd=backend_dir,
        )
        ready_line = proc.stdout.readline() if proc.stdout else ''
        try:
            ready = json.loads(ready_line) if ready_line else {}
        except ValueError:
            ready = {}
        if not ready.get('ready') or proc.poll() is not None:
            try:
                proc.kill()
            except Exception:
                pass
            raise RuntimeError((proc.stderr.read() if proc.stderr else '')[-600:] or 'Kokoro warm worker failed to start')
        _KOKORO_WORKERS[key] = proc
        return proc

    def generate_voice(self,text,voice,output_path,speed=1,profile=None,segments=None):
        import json,os
        runtime=Path(__file__).resolve().parents[3]/'generated/hybrid-review'
        python=Path(os.environ.get('KOKORO_PYTHON',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')))
        if not python.is_file() or not (runtime/'models/verified-int8.json').is_file():
            raise NarrationUnavailable('Approved local Kokoro runtime unavailable; no alternate narrator selected')
        payload={'runtime':str(runtime),'voice':voice,'text':text,'output':str(output_path),'speed':1,'alignment_required':True}
        line = json.dumps(payload) + '\n'
        with _KOKORO_LOCK:
            key = (str(python), str(runtime))
            for attempt in range(2):
                try:
                    proc = self._ensure_worker(python, runtime)
                    proc.stdin.write(line)
                    proc.stdin.flush()
                    reply_line = proc.stdout.readline()
                    if not reply_line:
                        raise BrokenPipeError('Kokoro warm worker closed stdout')
                    reply = json.loads(reply_line)
                    if not reply.get('ok'):
                        raise NarrationUnavailable('Approved Kokoro synthesis failed: ' + str(reply.get('error', 'unknown'))[-600:])
                    return 'Kokoro local narrator'
                except NarrationUnavailable:
                    raise
                except Exception:
                    dead = _KOKORO_WORKERS.pop(key, None)
                    if dead is not None:
                        try:
                            dead.kill()
                        except Exception:
                            pass
                    if attempt == 0:
                        continue
            backend_dir = str(Path(__file__).resolve().parents[2])
            result=subprocess.run([str(python),'-m','app.tts.kokoro_worker'],input=json.dumps(payload),encoding='utf8',capture_output=True,timeout=600,cwd=backend_dir)
            if result.returncode:raise NarrationUnavailable('Approved Kokoro synthesis failed: '+result.stderr[-600:])
            return 'Kokoro local narrator'


GEMINI_TTS_MODELS = ('gemini-2.5-flash-preview-tts', 'gemini-2.5-pro-preview-tts')
GEMINI_STYLE_PROMPTS = {
    'Newscaster': 'a crisp, authoritative newscaster style',
    'Documentary': 'an engaging documentary narrator style',
    'Storyteller': 'a vivid, captivating storyteller style',
    'Sports Hype': 'an energetic, punchy sports broadcast commentary style',
    'Conversational': 'a natural, conversational style',
    'Dramatic': 'a tense, dramatic investigative style',
    'Calm & Serious': 'a calm, measured, serious style',
}
GEMINI_PACE_PROMPTS = {
    'Rapid': 'a rapid pace',
    'Fast': 'a fast pace',
    'Normal': 'a natural steady pace',
    'Measured': 'a measured, clear pace',
}


def _gemini_tts_prompt(text: str, style: str, pace: str, accent: str) -> str:
    style_desc = GEMINI_STYLE_PROMPTS.get(style, style.strip() or 'a crisp, authoritative newscaster style')
    pace_desc = GEMINI_PACE_PROMPTS.get(pace, pace.strip() or 'a rapid pace')
    accent_clean = (accent or 'American English').strip()
    article = 'an' if accent_clean[:1].lower() in 'aeiou' else 'a'
    return f'Read aloud in {style_desc} with {pace_desc} and {article} {accent_clean} accent:\n\n{text}'


class GeminiTTSProvider:
    name = 'Gemini Studio TTS'

    def generate_voice(
        self,
        text,
        voice,
        output_path,
        speed=1,
        profile=None,
        segments=None,
        style='Newscaster',
        pace='Rapid',
        accent='American English',
        language='en-US',
    ):
        import re
        from app.ai.smart_router import _is_cooled_down, _mark_cooldown, parse_gemini_keys
        from app.video.alignment import write_acoustic_word_boundaries

        keys = parse_gemini_keys()
        if not keys:
            raise NarrationUnavailable('GEMINI_API_KEY is required for Gemini Studio Speech Generation')
        voice_name = (voice or '').strip() or 'Charon'
        style_val = (style or '').strip() or 'Newscaster'
        pace_val = (pace or '').strip() or 'Rapid'
        accent_val = (accent or '').strip() or 'American English'
        prompt = _gemini_tts_prompt(text, style_val, pace_val, accent_val)
        payload = {
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {
                'responseModalities': ['AUDIO'],
                'speechConfig': {
                    'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice_name}},
                },
            },
        }

        last_err = 'No available Gemini TTS key/model'
        pcm_bytes = None
        mime_type = 'audio/L16;codec=pcm;rate=24000'
        used_model = GEMINI_TTS_MODELS[0]
        for model in GEMINI_TTS_MODELS:
            for key in keys:
                cooldown_id = f'gemini-tts:{model}:{key[-6:]}'
                if _is_cooled_down(cooldown_id):
                    continue
                url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
                try:
                    resp = httpx.post(
                        url,
                        headers={'x-goog-api-key': key, 'Content-Type': 'application/json'},
                        json=payload,
                        timeout=90,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        parts = (((data.get('candidates') or [{}])[0].get('content') or {}).get('parts') or [])
                        inline = next((p.get('inlineData') for p in parts if p.get('inlineData') and p['inlineData'].get('data')), None)
                        if inline:
                            pcm_bytes = base64.b64decode(inline['data'])
                            mime_type = inline.get('mimeType') or mime_type
                            used_model = model
                            break
                        last_err = f'{model}: response contained no audio inlineData'
                    else:
                        msg = resp.text[:250]
                        last_err = f'{model} HTTP {resp.status_code}: {msg}'
                        if resp.status_code in {429, 503}:
                            _mark_cooldown(cooldown_id, 60)
                        elif resp.status_code in {400, 404}:
                            break
                except Exception as exc:
                    last_err = f'{model} {type(exc).__name__}: {exc}'
            if pcm_bytes:
                break

        if not pcm_bytes:
            raise NarrationUnavailable(f'Gemini Studio TTS failed: {last_err}')

        rate_match = re.search(r'rate=(\d+)', mime_type)
        sample_rate = int(rate_match.group(1)) if rate_match else 24000
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)

        write_acoustic_word_boundaries(output_path, text, provider=f'Gemini Studio TTS ({voice_name})')
        gen_meta = {
            'provider': 'gemini_tts',
            'model': used_model,
            'mime_type': mime_type,
            'sample_rate': sample_rate,
            'engine_controls': {
                'voice': voice_name,
                'style': style_val,
                'pace': pace_val,
                'accent': accent_val,
            },
        }
        output_path.with_suffix('.generation.json').write_text(json.dumps(gen_meta, indent=2), encoding='utf8')
        return f'Gemini Studio ({voice_name}, {style_val}, {pace_val}, {accent_val})'


def get_tts_provider(provider=None):
    name = provider or settings.tts_provider
    if name == 'gemini_tts':
        return GeminiTTSProvider()
    if name == 'kokoro_onnx':
        return KokoroTTSProvider()
    if name == 'google':
        return GoogleTTSProvider()
    if name == 'elevenlabs':
        return ElevenLabsProvider()
    return LocalTTSProvider()


def generate_narration(
    text,
    voice,
    path,
    provider='local',
    speed=1,
    profile=None,
    segments=None,
    language=None,
    metadata=None,
    voice_style='',
    voice_pace='',
    voice_accent='',
):
    if language is not None:
        # An explicit local request is a cost boundary, not permission to try a
        # configured paid provider if Windows speech fails.
        providers=['local'] if provider=='local' else ['elevenlabs','google','local'] if provider=='auto' else [provider]
        errors=[]
        for name in providers:
            if not configured(name): continue
            try:
                narrator=resolve_narrator(name,language,voice)
                tts=get_tts_provider(name)
                if name=='gemini_tts':
                    result=tts.generate_voice(
                        text, narrator.voice, path, speed, profile, segments,
                        style=voice_style or settings.title_short_voice_style,
                        pace=voice_pace or settings.title_short_voice_pace,
                        accent=voice_accent or settings.title_short_voice_accent,
                        language=language,
                    )
                else:
                    result=tts.generate_voice(text,narrator.voice,path,speed,profile,segments)
                if 'fallback' in result.lower():
                    raise NarrationUnavailable('Speech engine could not produce narration')
                if metadata is not None:
                    metadata.update(provider=name,voice=narrator.voice,locale=narrator.locale,reason=narrator.reason)
                    if name=='gemini_tts':
                        metadata.update(
                            voice_style=voice_style or settings.title_short_voice_style,
                            voice_pace=voice_pace or settings.title_short_voice_pace,
                            voice_accent=voice_accent or settings.title_short_voice_accent,
                        )
                return result
            except Exception as exc:
                errors.append(f'{name}: {type(exc).__name__}')
                logger.warning('Compatible narration failed provider=%s language=%s type=%s',name,language,type(exc).__name__)
        from app.core.languages import language_info
        raise NarrationUnavailable(f'No compatible narration available for {language_info(language).name} ({language}). '
                                   'Install a matching local voice or configure a compatible Google/ElevenLabs narrator. '+', '.join(errors))
    try:
        tts=get_tts_provider(provider)
        if provider=='gemini_tts':
            return tts.generate_voice(
                text, voice, path, speed, profile, segments,
                style=voice_style or settings.title_short_voice_style,
                pace=voice_pace or settings.title_short_voice_pace,
                accent=voice_accent or settings.title_short_voice_accent,
            )
        return tts.generate_voice(text,voice,path,speed,profile,segments)
    except Exception as exc:
        if provider in {'kokoro_onnx','gemini_tts'}:raise NarrationUnavailable(f'Approved {provider} failed; narrator fallback is disabled') from exc
        logger.warning('Configured TTS unavailable (%s); trying local narration',type(exc).__name__)
        result=LocalTTSProvider().generate_voice(text,voice,path,speed,profile,segments)
        return result + ' (cloud unavailable; local selected)'
