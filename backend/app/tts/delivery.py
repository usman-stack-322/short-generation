"""Provider allowlists and fact-preserving scene-aware narration preparation."""
import re
from html import escape
from app.tts.director import VoiceProfile


def provider_controls(provider, profile, speed=1, voice_name=''):
    profile = VoiceProfile.model_validate(profile)
    pace = min(1.2, max(.7, speed * profile.pace))
    if provider == 'kokoro_onnx':
        return {'speed':1.0,'sentence_pause':.22,'clause_pause':.10}
    if provider == 'local':
        return {'rate': round(155 * pace), 'volume': profile.volume, 'speed': pace}
    if provider == 'google':
        # These established voice families support the SSML/prosody used below.
        supported = any(family in voice_name for family in ('Standard-', 'Wavenet-', 'Neural2-'))
        return ({'speakingRate': pace, 'pitch': round(profile.pitch * 20, 2),
                 'volumeGainDb': round((profile.volume - 1) * 12, 2)} if supported else {})
    if provider == 'elevenlabs':
        if profile.style in {'documentary','conversational'}:
            return {'stability':.5,'similarity_boost':.75,'style':.1,'speed':min(1.2,max(.7,speed))}
        # Existing fixed eleven_multilingual_v2 model supports precisely these settings.
        return {'stability': round(.75 - profile.energy * .25, 2), 'similarity_boost': .75,
                'style': round(profile.emphasis_strength * .3, 2), 'speed': pace}
    raise ValueError('Unsupported TTS provider')


def prepare_delivery(text, profile, scenes=(), hook=''):
    """Keep original sentences verbatim; never synthesize instructions as spoken words."""
    profile = VoiceProfile.model_validate(profile)
    emphasis = [s.get('emphasis_word', '') for s in scenes if s.get('emphasis_word')]
    sentences = re.findall(r'[^.!?]+[.!?]*\s*', text) or [text]
    segments = []
    for index, sentence in enumerate(sentences):
        role = 'hook' if index == 0 else 'ending' if index == len(sentences)-1 else 'context' if index == 1 else 'main_story'
        emphasis_word = next((word for word in emphasis if re.search(r'\b'+re.escape(word)+r'\b', sentence, re.I)), '')
        segments.append({'text': sentence, 'role': role, 'emphasis_word': emphasis_word,
                         'rate_multiplier': 1.02 if role == 'hook' else .98 if role == 'context' else 1,
                         'pause_ms': round(100 + profile.pause_strength * (200 if emphasis_word else 100))})
    return segments


def google_ssml(segments, profile):
    body = []
    for segment in segments:
        text = escape(segment['text'])
        word = segment['emphasis_word']
        if word and profile.emphasis_strength > .5:
            text = re.sub(re.escape(escape(word)), lambda m: '<emphasis level="moderate">'+m.group(0)+'</emphasis>', text, count=1, flags=re.I)
        body.append(f'<s><prosody rate="{round(segment["rate_multiplier"]*100)}%">{text}</prosody></s>')
        body.append(f'<break time="{segment["pause_ms"]}ms"/>')
    return '<speak>' + ''.join(body) + '</speak>'
