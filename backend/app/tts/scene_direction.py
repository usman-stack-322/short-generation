"""Separate editorial voice intent from engine capabilities."""
ARCS = {
    'hook': ('curious and confident', .7, 1.02, 180),
    'context': ('conversational and measured', .45, .98, 220),
    'reflection': ('restrained and serious', .35, .96, 260),
    'achievement': ('bright without shouting', .75, 1.03, 200),
    'closing': ('confident and satisfying', .55, .99, 280),
}

def narration_plan(scenes, narrator, provider):
    if not narrator or provider not in {'kokoro_onnx', 'local', 'google', 'elevenlabs'}:
        raise ValueError('Choose one explicit narrator and provider')
    rows = []
    for i, scene in enumerate(scenes):
        role = scene['purpose']
        emotion, intensity, pace, pause = ARCS[role]
        text = scene['text'].strip()
        if not text: raise ValueError('Every scene needs real narration text')
        rows.append({'scene': i+1, 'text': text, 'purpose': role,
                     'emotion_target': emotion, 'intensity_target': intensity,
                     'pace_target': pace, 'pause_after_ms_target': pause,
                     'emphasis_words': scene.get('emphasis_words', []),
                     'pronunciation_notes': scene.get('pronunciation_notes', []), 'narrator': narrator})
    return {'provider': provider, 'narrator': narrator, 'scenes': rows,
            'script': ' '.join(row['text'] for row in rows),
            'synthesis_strategy': 'coherent full script; one identity',
            'engine_controls': ({'voice': narrator, 'lang': 'en-gb', 'speed': 1.0,
                                 'sentence_pause': .22, 'clause_pause': .10}
                                if provider == 'kokoro_onnx' else {}),
            'unsupported_controls': (['emotion instructions', 'per-word emphasis',
                                      'per-scene intensity in full-script synthesis']
                                     if provider in {'kokoro_onnx', 'local'} else []),
            'direction_application': 'Spoken wording and punctuation carry the arc. Targets are editorial intent, not claimed engine emotion controls.',
            'naturalness_approved': False}
