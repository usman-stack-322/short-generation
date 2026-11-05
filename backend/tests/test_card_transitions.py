from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from app.video import renderer


def test_text_card_timeline_has_clean_cuts_and_exact_scene_lengths(tmp_path,monkeypatch):
    font=tmp_path/'font.ttf';font.write_bytes(b'fixture')
    monkeypatch.setattr(renderer,'resolve_font',lambda *a:SimpleNamespace(path=font))
    monkeypatch.setattr(renderer,'write_subtitles',lambda *a:None)
    monkeypatch.setattr(renderer,'audio_duration',lambda *a:3)
    monkeypatch.setattr(renderer,'validate_narration',lambda *a:None)
    monkeypatch.setattr(renderer,'create_cover',lambda *a,**k:tmp_path/'cover.png')
    commands=[];monkeypatch.setattr(renderer,'run',lambda command,**k:commands.append(command))
    slides=[]
    for i in range(2):
        path=tmp_path/f'{i}.jpg';Image.new('RGB',(100,100)).save(path);slides.append(path)
    scenes=[SimpleNamespace(start_time=0,end_time=1.5),SimpleNamespace(start_time=1.5,end_time=2.4)]
    import pytest
    with pytest.raises(ValueError,match='standalone text cards'):
        renderer.render_video('job','topic','subject','script',tmp_path/'voice.wav',30,tmp_path,slides,scenes=scenes,slide_kinds=['text_card','text_card'])
    assert not commands
