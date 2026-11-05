import pytest
from app.tts import providers,capabilities
from app.tts.capabilities import NarrationUnavailable
from app.tts.delivery import provider_controls
from app.tts.director import VoiceProfile

def test_explicit_kokoro_never_falls_back_to_other_narrator(monkeypatch,tmp_path):
    class Broken:
        def generate_voice(self,*a,**k):raise RuntimeError('missing runtime')
    monkeypatch.setattr(providers,'get_tts_provider',lambda *a:Broken())
    monkeypatch.setattr(providers.LocalTTSProvider,'generate_voice',lambda *a,**k:pytest.fail('Narrator changed'))
    with pytest.raises(NarrationUnavailable,match='fallback is disabled'):
        providers.generate_narration('Exact script.','bm_george',tmp_path/'voice.wav',provider='kokoro_onnx')

def test_explicit_kokoro_language_selection_is_local(monkeypatch):
    monkeypatch.setattr(capabilities,'configured',lambda _:True)
    voice=capabilities.resolve_narrator('kokoro_onnx','en-US','bm_george')
    assert voice.voice=='bm_george' and voice.locale=='en-GB'
    with pytest.raises(NarrationUnavailable,match='English only'):
        capabilities.resolve_narrator('kokoro_onnx','fr-FR','bm_george')

def test_kokoro_controls_match_accepted_henry_not_emotion_labels():
    controls=provider_controls('kokoro_onnx',VoiceProfile(),speed=1.2)
    assert controls=={'speed':1.,'sentence_pause':.22,'clause_pause':.10}
    assert 'emotion' not in controls and 'pitch' not in controls
