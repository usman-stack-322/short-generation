import array
import base64
import json
import math
import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.models import CelebrityAsset, CelebrityFolder
from app.services.celebrity_vault import _parse_celebrity_and_mood, match_celebrity_asset, scan_celebrity_folder
from app.services.title_shorts import TitleInput
from app.tts import capabilities, providers
from app.video.alignment import load_boundaries, write_acoustic_word_boundaries
from app.video.editorial import edit_timeline
from app.video.subtitles import write_subtitles


def _write_tone_wav(path: Path, segments_ms: list[tuple[bool, int]], sr: int = 24000):
    frames = array.array('h')
    sample_idx = 0
    for is_speech, dur_ms in segments_ms:
        n = int(sr * dur_ms / 1000)
        for _ in range(n):
            val = int(5000 * math.sin(2 * math.pi * 220 * sample_idx / sr)) if is_speech else 0
            frames.append(val)
            sample_idx += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(frames.tobytes())
    return frames.tobytes()


def test_vault_parser_cleans_subfolders_and_drive_noise(tmp_path):
    root = tmp_path / 'vault'
    assert _parse_celebrity_and_mood(root, root / 'Stephen A. Smith' / 'int' / 'Rec 0001.mp4')[0] == 'Stephen A. Smith'
    assert _parse_celebrity_and_mood(root, root / 'Kobe Bryant' / 'kobe bryants interview' / '1.mp4') == ('Kobe Bryant', ['interview'])
    assert _parse_celebrity_and_mood(root, root / '50 CENT' / 'New folder' / '1695.jpg')[0] == '50 Cent'
    assert _parse_celebrity_and_mood(root, root / 'Austin Reaves →' / 'Rec 0027.mp4')[0] == 'Austin Reaves'
    assert _parse_celebrity_and_mood(root, root / 'Ryan Davis-20261022T164103Z-1-001' / 'Ryan Davis' / 'Rec 0001.mp4')[0] == 'Ryan Davis'


def test_vault_matcher_prefers_stephen_a_smith_and_blocks_missing_person_hijack(tmp_path):
    from app.database.session import Base, SessionLocal, engine
    from app.models import Workspace
    from app.core.security import new_id
    Base.metadata.create_all(bind=engine)

    vault = tmp_path / 'vault'
    (vault / 'Stephen A. Smith').mkdir(parents=True)
    (vault / 'Stephen A. Smith' / 'Rec 0001.mp4').write_bytes(b'clip1-bytes')
    (vault / 'Stephen A. Smith' / 'Rec 0002.mp4').write_bytes(b'clip2-bytes')
    (vault / 'JOE BUDDEN' / 'int').mkdir(parents=True)
    (vault / 'JOE BUDDEN' / 'int' / 'Rec 0009.mp4').write_bytes(b'joe-int-bytes')
    (vault / 'basketball highlights').mkdir(parents=True)
    (vault / 'basketball highlights' / 'Rec 0001.mp4').write_bytes(b'bball-bytes')

    ws_id = new_id()
    with SessionLocal() as db:
        db.add(Workspace(id=ws_id, name='Test Vault WS'))
        db.commit()
        scan_celebrity_folder(db, ws_id, str(vault), 'mix_both')

        draft_dir = tmp_path / 'draft_assets'
        scene1 = {
            'number': 1,
            'narration': 'Kevin Garnett confronted Stephen A. Smith in an intense exchange.',
            'visual_description': 'Kevin Garnett and Stephen A. Smith in an intense conversation.',
            'image_query': 'Kevin Garnett Stephen A Smith face to face',
        }
        m1 = match_celebrity_asset(db, ws_id, scene1, draft_dir, draft_title='Garnett & Smith', people=['Kevin Garnett', 'Stephen A. Smith'])
        assert m1 and m1['celebrity_name'] == 'Stephen A. Smith'

        # Scene featuring ONLY missing Kevin Garnett must return None so Real Web Photo Fallback finds him!
        scene2 = {
            'number': 2,
            'narration': 'Garnett challenged the ongoing basketball media criticism.',
            'visual_description': 'Close up of Kevin Garnett speaking intently.',
            'image_query': 'Kevin Garnett speaking intently basketball analyst',
        }
        m2 = match_celebrity_asset(db, ws_id, scene2, draft_dir, draft_title='Garnett & Smith', people=['Kevin Garnett', 'Stephen A. Smith'], existing=[m1])
        assert m2 is None

        # Scene 3 featuring Stephen A. Smith must pick the SECOND clip rather than repeating clip 1
        scene3 = {
            'number': 3,
            'narration': 'The disagreement spotlighted Stephen A. Smith reacting.',
            'visual_description': 'Stephen A. Smith listening and reacting.',
            'image_query': 'Stephen A Smith reacting studio',
        }
        m3 = match_celebrity_asset(db, ws_id, scene3, draft_dir, draft_title='Garnett & Smith', people=['Kevin Garnett', 'Stephen A. Smith'], existing=[m1, None])
        assert m3 and m3['celebrity_name'] == 'Stephen A. Smith'
        assert m3['vault_asset_id'] != m1['vault_asset_id']

        db.query(CelebrityAsset).filter_by(workspace_id=ws_id).delete()
        db.query(CelebrityFolder).filter_by(workspace_id=ws_id).delete()
        db.query(Workspace).filter_by(id=ws_id).delete()
        db.commit()


def test_acoustic_alignment_tracks_real_speech_islands_and_validates(tmp_path):
    wav = tmp_path / 'speech.wav'
    # 200ms lead silence, 500ms first clause speech, 700ms pause, 600ms second clause speech, 100ms tail silence
    _write_tone_wav(wav, [(False, 200), (True, 500), (False, 700), (True, 600), (False, 100)])
    script = 'First clause! Second clause.'
    data = write_acoustic_word_boundaries(wav, script, 'Gemini Studio TTS')
    assert load_boundaries(wav, script) is not None
    words = data['words']
    assert len(words) == 4
    # First word must start near 0.2s active speech onset (not 0.0s)
    assert words[0]['start'] >= 0.15
    # Second clause must jump past the 0.7s..1.4s pause island (~1.4s)
    assert words[2]['start'] >= 1.25


def test_gemini_tts_provider_and_studio_controls(monkeypatch, tmp_path):
    monkeypatch.setattr('app.ai.smart_router.parse_gemini_keys', lambda: ['test-key-123456'])
    assert capabilities.configured('gemini_tts') is True
    voices = [v for v in capabilities.list_voice_options() if v['provider'] == 'gemini_tts']
    assert any(v['voice'] == 'Charon' for v in voices) and len(voices) >= 30

    wav_fixture = tmp_path / 'pcm_fixture.wav'
    pcm_raw = _write_tone_wav(wav_fixture, [(True, 900)])
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured['url'] = url
        captured['payload'] = json
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                'candidates': [{
                    'content': {
                        'parts': [{
                            'inlineData': {
                                'mimeType': 'audio/L16;codec=pcm;rate=24000',
                                'data': base64.b64encode(pcm_raw).decode('ascii'),
                            }
                        }]
                    }
                }]
            },
        )

    monkeypatch.setattr(providers.httpx, 'post', fake_post)
    out = tmp_path / 'gemini_out.wav'
    meta = {}
    script = 'Kevin Garnett confronted Stephen A. Smith.'
    label = providers.generate_narration(
        script,
        'Charon',
        out,
        provider='gemini_tts',
        language='en-US',
        metadata=meta,
        voice_style='Newscaster',
        voice_pace='Rapid',
        voice_accent='American English',
    )
    assert 'Gemini Studio' in label
    assert captured['payload']['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'] == 'Charon'
    prompt_text = captured['payload']['contents'][0]['parts'][0]['text']
    assert 'newscaster style' in prompt_text.lower()
    assert 'rapid pace' in prompt_text.lower()
    assert 'american english' in prompt_text.lower()
    assert out.is_file() and load_boundaries(out, script) is not None
    gen = json.loads(out.with_suffix('.generation.json').read_text(encoding='utf8'))
    assert gen['provider'] == 'gemini_tts'
    assert gen['engine_controls'] == {
        'voice': 'Charon',
        'style': 'Newscaster',
        'pace': 'Rapid',
        'accent': 'American English',
    }
    assert meta['voice_style'] == 'Newscaster' and meta['voice_pace'] == 'Rapid'

    payload = TitleInput(
        title='Kevin Garnett confronting Stephen A. Smith on air',
        narrator='gemini_tts',
        voice='Charon',
        voice_style='Newscaster',
        voice_pace='Rapid',
        voice_accent='American English',
        caption_style='viral_gold',
    )
    assert payload.caption_style == 'viral_gold'


def test_viral_captions_and_dynamic_transitions(tmp_path):
    script = 'Kevin Garnett confronted Stephen A. Smith.'
    wav = tmp_path / 'timed.wav'
    _write_tone_wav(wav, [(True, 3200)])
    timing = write_acoustic_word_boundaries(wav, script, 'Gemini Studio TTS')
    ass = tmp_path / 'captions.ass'
    srt = tmp_path / 'captions.srt'
    write_subtitles(script, 3.4, ass, srt, {'language': 'en-US', 'narration_timing': timing, 'caption_style': 'viral_gold'})
    body = ass.read_text(encoding='utf8')
    assert 'Arial Black,82,' in body
    assert r'\c&H00E6FF&\fscx112\fscy112' in body
    assert body.count('Dialogue:') == 6  # Timed word highlight for all 6 spoken words

    plans = [
        {'text': 'Kevin Garnett confronted', 'transition_in': 'cut'},
        {'text': 'Stephen A. Smith.', 'transition_in': 'smoothleft'},
    ]
    _, changes, _ = edit_timeline(4.0, 2, timing=timing, script=script, scene_plan=plans)
    assert changes[0]['type'] == 'dissolve'
    assert changes[0]['transition'] == 'smoothleft'
    assert changes[0]['duration'] == pytest.approx(0.45)
