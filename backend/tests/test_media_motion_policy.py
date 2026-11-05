from types import SimpleNamespace
from pathlib import Path
import pytest
from app.video import renderer

@pytest.fixture
def render_graph(tmp_path,monkeypatch):
    font=tmp_path/'font.ttf';font.write_bytes(b'fixture')
    monkeypatch.setattr(renderer,'resolve_font',lambda *a:SimpleNamespace(path=font))
    monkeypatch.setattr(renderer,'write_subtitles',lambda *a:None)
    monkeypatch.setattr(renderer,'audio_duration',lambda *a:12)
    monkeypatch.setattr(renderer,'validate_narration',lambda *a:None)
    monkeypatch.setattr('app.video.final_audio.finalize_narration',lambda audio,*a:(audio,None,{}))
    monkeypatch.setattr(renderer,'create_cover',lambda *a,**k:tmp_path/'cover.png')
    monkeypatch.setattr('app.video.photo_framing.compose_photo',lambda *a,**k:{'treatment':'fixture'})
    commands=[];monkeypatch.setattr(renderer,'run',lambda command,**k:commands.append(command))
    return tmp_path,commands

def test_natural_narration_motion_and_clip_audio_isolation(render_graph):
    root,commands=render_graph
    renderer.render_video('job','topic','subject','Complete script.',root/'voice.wav',30,root,[root/'one.jpg',root/'two.jpg',root/'clip.mp4'],slide_kinds=['archive','archive','clip'])
    command=commands[0];graph=command[command.index('-filter_complex')+1]
    assert 'atempo=' not in graph
    assert '1.01+0.12*' in graph and '1.13-0.12*' in graph and 'cos(PI*on/' in graph
    assert '[2:a]' not in graph and '[3:a]' in graph
    assert command[command.index('-t',command.index('-filter_complex'))+1]=='12.12'
    assert 'xfade' in graph

def test_long_narration_holds_instead_of_cutting(render_graph,monkeypatch):
    root,commands=render_graph
    monkeypatch.setattr(renderer,'audio_duration',lambda *a:31)
    with pytest.raises(ValueError,match='configured duration limit'):
        renderer.render_video('job','topic','subject','Complete script.',root/'voice.wav',30,root,[root/'one.jpg'])
    assert not commands

def test_missing_media_cannot_render_on_retry(render_graph):
    root,commands=render_graph
    with pytest.raises(ValueError,match='Missing genuine'):
        renderer.render_video('job','topic','subject','Script',root/'voice.wav',30,root,[root/'held.jpg'],slide_kinds=['missing'])
    assert not commands

def test_local_failure_never_returns_successful_silence(tmp_path,monkeypatch):
    from app.tts.providers import LocalTTSProvider
    from app.tts.capabilities import NarrationUnavailable
    monkeypatch.setattr('app.tts.providers.subprocess.run',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('driver unavailable')))
    with pytest.raises(NarrationUnavailable):
        LocalTTSProvider().generate_voice('Complete text','en-US',tmp_path/'voice.wav')


def test_scene_timeline_follows_complete_narration(render_graph):
    import json
    root,commands=render_graph
    scenes=[SimpleNamespace(start_time=0,end_time=10),SimpleNamespace(start_time=10,end_time=30)]
    renderer.render_video('job','topic','subject','Script',root/'voice.wav',30,root,[root/'one.jpg',root/'two.jpg'],scenes=scenes)
    timeline=json.loads((root/'videos/job/render-timeline.json').read_text())
    assert timeline['duration']==12.12
    assert timeline['scenes'][0]['end']==pytest.approx(4.04)
    assert timeline['scenes'][-1]['end']==12.12


def test_cached_silent_narration_is_rejected_before_render(tmp_path):
    import wave
    path=tmp_path/'cached.wav'
    with wave.open(str(path),'wb') as audio:
        audio.setparams((1,2,16000,0,'NONE','not compressed'))
        audio.writeframes(b'\0\0'*16000)
    with pytest.raises(ValueError,match='silent or inaudible'):
        renderer.validate_narration(path)
