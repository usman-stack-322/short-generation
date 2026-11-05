"""Deterministic delivery direction; never changes facts or narrator identity."""
import logging
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

VoiceStyle = Literal['professional', 'news', 'documentary', 'energetic', 'funny',
                     'emotional', 'motivational', 'educational', 'dramatic', 'luxury',
                     'conversational', 'sports_hype', 'serious']
VoiceSelection = Literal['auto', 'professional', 'news', 'documentary', 'energetic',
                         'funny', 'emotional', 'motivational', 'educational', 'dramatic',
                         'luxury', 'conversational', 'sports_hype', 'serious']
VoiceProvider = Literal['auto', 'local', 'google', 'elevenlabs', 'kokoro_onnx']


class VoiceProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    style: VoiceStyle = 'professional'
    tone: str = Field(default='clear_confident', min_length=1, max_length=100)
    pace: float = Field(default=1, ge=.85, le=1.15)
    energy: float = Field(default=.5, ge=0, le=1)
    pitch: float = Field(default=0, ge=-.2, le=.2)
    volume: float = Field(default=1, ge=.1, le=1)
    pause_strength: float = Field(default=.5, ge=0, le=1)
    emphasis_strength: float = Field(default=.5, ge=0, le=1)
    emotion: str = Field(default='neutral', min_length=1, max_length=80)
    auto_selected: bool = True
    reason: str = Field(default='Neutral professional narration.', min_length=1, max_length=500)
    language_code: str = 'en-US'
    locale: str = 'en-US'


PRESETS = {
    'professional': ('clear_confident', 1, .5, 'neutral'),
    'news': ('serious_alert', 1.06, .72, 'focused'),
    'documentary': ('authoritative_cinematic', .96, .5, 'reflective'),
    'energetic': ('upbeat_confident', 1.06, .8, 'excited'),
    'funny': ('playful_conversational', 1.05, .68, 'amused'),
    'emotional': ('warm_empathetic', .92, .35, 'reflective'),
    'motivational': ('confident_inspiring', 1.03, .8, 'inspired'),
    'educational': ('clear_patient', .98, .5, 'curious'),
    'dramatic': ('measured_cinematic', .95, .65, 'anticipation'),
    'luxury': ('relaxed_polished', .96, .45, 'composed'),
    'conversational': ('warm_natural', 1, .5, 'friendly'),
    'sports_hype': ('excited_confident', 1.08, .85, 'excited'),
    'serious': ('calm_respectful', .95, .35, 'serious'),
}


def _has(text, expression):
    return bool(re.search(r'\b(?:' + expression + r')\b', text, re.I))


def analyze(topic, script, personality='', category='', tone='', scenes=()):
    # Actual topic and spoken content outrank the theme's usual tone/category.
    words = ' '.join(str(script.get(k, '')) for k in
                     ('hook', 'context', 'main_story', 'why_it_matters', 'ending'))
    actual = f'{topic} {words or script.get("full_script", "")}'
    sports = _has(f'{actual} {category} {personality}', r'sports?|football|basketball|Ronaldo|Messi|NBA|tactical')
    if _has(actual, r'death|died|arrest|injur\w*|medical|legal dispute|tragedy'):
        return 'serious', 'Sensitive factual content calls for calm, respectful delivery.'
    if _has(actual, r'breaking|just announced|latest news|urgent'):
        return 'news', 'The script presents a timely announcement or breaking-news update.'
    if _has(actual, r'emotional|retirement|retrospective|farewell|heartfelt|grief'):
        return 'emotional', 'The story is an emotional career retrospective or farewell.'
    if _has(actual, r'funny|comedy|hilarious|joke|bloopers?|humorous'):
        return 'funny', 'The script describes a playful or humorous moment.'
    if _has(actual, r'analysis|tactical|analyzing|analysing|detailed breakdown'):
        return 'professional', 'The topic calls for clear, confident analysis rather than hype.'
    if _has(actual, r'explained|educational|how to|why does|tutorial|learn|explanation'):
        return 'educational', 'The script teaches or explains a concept.'
    if sports and _has(actual, r'achievement|record|champion|triumph|milestone|wins?|victory'):
        return 'sports_hype', 'The script covers a major sports achievement or milestone.'
    if _has(actual, r'motivational|never give up|perseverance|inspire|determination'):
        return 'motivational', 'The story emphasizes perseverance and inspiration.'
    if _has(actual, r'luxury|yacht|mansion|luxurious'):
        return 'luxury', 'The story explores luxury and lifestyle.'
    if _has(actual, r'dramatic|suspense|unexpected reveal'):
        return 'dramatic', 'The script builds anticipation around a reveal.'
    if _has(actual, r'energetic|upbeat|high energy'):
        return 'energetic', 'The script calls for an upbeat, energetic delivery.'
    if _has(actual, r'conversational|casual chat|friendly conversation'):
        return 'conversational', 'The script uses a friendly conversational approach.'
    # Scene hints are weaker than explicit spoken content and theme hints are last.
    hints = ' '.join(str(s.get('caption', '')) for s in scenes)
    if _has(hints, r'educational|explained'):
        return 'educational', 'The scene plan supports an explanatory delivery.'
    if _has(f'{category} {tone}', r'business|documentary|history|biography'):
        return 'documentary', 'The theme suggests measured documentary narration.'
    return 'professional', 'A balanced professional delivery suits this script.'


def direct_voice(topic, script, personality='', category='', tone='', scenes=(), selection='auto', content_type='', language='en-US'):
    from app.core.languages import language_info
    locale=language_info(language).code
    try:
        if selection == 'auto':
            style, reason = analyze(topic, script, personality, f'{category} {content_type}', tone, scenes)
        else:
            style, reason = selection, 'Manually selected narration delivery.'
        voice_tone, pace, energy, emotion = PRESETS[style]
        if locale in {'ur-PK','ar-SA','zh-CN','hi-IN'}:
            pace=min(pace,1.04)  # Favor clarity for these scripts while retaining style/energy.
        return VoiceProfile(style=style, tone=voice_tone, pace=pace, energy=energy,
                            language_code=locale,locale=locale,
                            emotion=emotion, auto_selected=selection == 'auto', reason=reason,
                            pause_strength=.7 if style in {'emotional', 'dramatic'} else .5,
                            emphasis_strength=.8 if style == 'sports_hype' else .5)
    except Exception:
        logging.getLogger(__name__).exception('Voice direction failed; using neutral professional delivery')
        return VoiceProfile(language_code=locale,locale=locale,reason='Automatic analysis unavailable; neutral professional delivery selected.')
