from unittest.mock import Mock
import pytest
from app.tts import providers
from app.tts.capabilities import NarrationUnavailable


def test_explicit_local_failure_never_attempts_configured_cloud(monkeypatch,tmp_path):
    attempted=[]
    monkeypatch.setattr(providers,'configured',lambda name:True)
    def resolve(name,*args):
        attempted.append(name)
        raise NarrationUnavailable('Local test voice unavailable')
    monkeypatch.setattr(providers,'resolve_narrator',resolve)
    cloud=Mock(side_effect=AssertionError('No cloud requests authorized'))
    monkeypatch.setattr(providers,'get_tts_provider',cloud)
    with pytest.raises(NarrationUnavailable):
        providers.generate_narration('English text','en-US',tmp_path/'voice.wav','local',language='en-US')
    assert attempted==['local'] and not cloud.called
