import json,hashlib
from app.video.alignment import load_boundaries,aligned_cues
from app.video.subtitles import write_subtitles

def timing(audio,script):
    words=[{'char':0,'length':5,'text':'First','start':.2},{'char':6,'length':6,'text':'second','start':1.3},{'char':13,'length':5,'text':'third','start':2.8}]
    data={'provider':'Native fixture boundaries','audio_sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(script.encode()).hexdigest(),'duration':4,'words':words}
    audio.with_suffix('.words.json').write_text(json.dumps(data));return data

def test_exact_audio_and_script_required_for_native_boundaries(tmp_path):
    audio=tmp_path/'voice.wav';audio.write_bytes(b'fixture audio');script='First second third'
    timing(audio,script);assert load_boundaries(audio,script)
    assert load_boundaries(audio,script+' changed') is None
    audio.write_bytes(b'different revision');assert load_boundaries(audio,script) is None

def test_native_gaps_are_retained_instead_of_equal_word_durations(tmp_path):
    audio=tmp_path/'voice.wav';audio.write_bytes(b'fixture');script='First second third';data=timing(audio,script)
    cues=aligned_cues(script,8,data,1)
    assert cues==[(.4,2.6,'First'),(2.6,5.6,'second'),(5.6,8,'third')]
    ass=tmp_path/'captions.ass';srt=tmp_path/'captions.srt'
    write_subtitles(script,8,ass,srt,{'narration_timing':data,'max_words':1,'subtitle_mode':'word-highlight'})
    assert '00:00:02,600 --> 00:00:05,600' in srt.read_text()
    assert ass.read_text().count('Dialogue:')==3

def test_incomplete_or_backwards_native_events_rejected(tmp_path):
    audio=tmp_path/'voice.wav';audio.write_bytes(b'fixture');script='First second third';data=timing(audio,script)
    data['words'].pop();audio.with_suffix('.words.json').write_text(json.dumps(data));assert load_boundaries(audio,script) is None
    data=timing(audio,script);data['words'][1]['start']=.1;audio.with_suffix('.words.json').write_text(json.dumps(data));assert load_boundaries(audio,script) is None
