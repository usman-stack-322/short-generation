"""Narrator providers. Celebrity voice cloning is deliberately unsupported."""
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

class KokoroTTSProvider:
    """Explicit local provider; no cloud or narrator fallback."""
    def generate_voice(self,text,voice,output_path,speed=1,profile=None,segments=None):
        import json,os
        runtime=Path(__file__).resolve().parents[3]/'generated/hybrid-review'
        python=Path(os.environ.get('KOKORO_PYTHON',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')))
        if not python.is_file() or not (runtime/'models/verified-int8.json').is_file():
            raise NarrationUnavailable('Approved local Kokoro runtime unavailable; no alternate narrator selected')
        payload={'runtime':str(runtime),'voice':voice,'text':text,'output':str(output_path),'speed':1,'alignment_required':True}
        result=subprocess.run([str(python),'-m','app.tts.kokoro_worker'],input=json.dumps(payload),encoding='utf8',capture_output=True,timeout=1200)
        if result.returncode:raise NarrationUnavailable('Approved Kokoro synthesis failed: '+result.stderr[-600:])
        return 'Kokoro local narrator'


def get_tts_provider(provider=None):
    if (provider or settings.tts_provider)=='kokoro_onnx':return KokoroTTSProvider()
    if (provider or settings.tts_provider) == 'google':
        return GoogleTTSProvider()
    if (provider or settings.tts_provider) == 'elevenlabs':
        return ElevenLabsProvider()
    return LocalTTSProvider()


def generate_narration(text,voice,path,provider='local',speed=1,profile=None,segments=None,language=None,metadata=None):
    if language is not None:
        # An explicit local request is a cost boundary, not permission to try a
        # configured paid provider if Windows speech fails.
        providers=['local'] if provider=='local' else ['elevenlabs','google','local'] if provider=='auto' else [provider]
        errors=[]
        for name in providers:
            if not configured(name): continue
            try:
                narrator=resolve_narrator(name,language,voice)
                result=get_tts_provider(name).generate_voice(text,narrator.voice,path,speed,profile,segments)
                if 'fallback' in result.lower():
                    raise NarrationUnavailable('Speech engine could not produce narration')
                if metadata is not None:
                    metadata.update(provider=name,voice=narrator.voice,locale=narrator.locale,reason=narrator.reason)
                return result
            except Exception as exc:
                errors.append(f'{name}: {type(exc).__name__}')
                logger.warning('Compatible narration failed provider=%s language=%s type=%s',name,language,type(exc).__name__)
        from app.core.languages import language_info
        raise NarrationUnavailable(f'No compatible narration available for {language_info(language).name} ({language}). '
                                   'Install a matching local voice or configure a compatible Google/ElevenLabs narrator. '+', '.join(errors))
    try:
        return get_tts_provider(provider).generate_voice(text,voice,path,speed,profile,segments)
    except Exception as exc:
        if provider=='kokoro_onnx':raise NarrationUnavailable('Approved local Kokoro failed; narrator fallback is disabled') from exc
        logger.warning('Configured TTS unavailable (%s); trying local narration',type(exc).__name__)
        result=LocalTTSProvider().generate_voice(text,voice,path,speed,profile,segments)
        return result + ' (cloud unavailable; local selected)'
