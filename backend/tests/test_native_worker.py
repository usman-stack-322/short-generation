import os,sys,subprocess,wave,json
import pytest
from app.video.alignment import load_boundaries

@pytest.mark.skipif(os.name!='nt',reason='Windows local narrator integration')
def test_native_word_times_use_the_actual_wave_format(tmp_path):
    path=tmp_path/'native.wav';text='First second third.'
    subprocess.run([sys.executable,'-m','app.tts.local_worker',str(path),'en-US','1','1'],input=text,encoding='utf8',check=True,capture_output=True,timeout=75)
    with wave.open(str(path),'rb') as audio:
        assert audio.getframerate()==16000
        duration=audio.getnframes()/audio.getframerate()
    timing=load_boundaries(path,text)
    assert timing and len(timing['words'])>=3
    assert timing['words'][-1]['start']<duration
