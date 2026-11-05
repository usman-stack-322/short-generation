import sys
import json
import pyttsx3
import os
import wave
import hashlib
import subprocess
from pathlib import Path

def main():
    engine = pyttsx3.init()
    if sys.argv[1]=='--list':
        result=[{'id':v.id,'name':v.name,'languages':[str(lang.decode('utf-8',errors='ignore') if isinstance(lang,bytes) else lang).lstrip(''.join(chr(i) for i in range(32))) for lang in v.languages]} for v in engine.getProperty('voices')]
        print(json.dumps(result,ensure_ascii=True))
        engine.stop()
        return
    language = sys.argv[2].split('-')[0].lower()
    voices = engine.getProperty('voices')
    exact = [v for v in voices if sys.argv[2] in (v.id, v.name)]
    matching = exact or [v for v in voices if language in str(v.languages).lower() or
                {'en': 'english', 'es': 'spanish', 'fr': 'french'}.get(language, language) in v.name.lower()]
    if matching:
        engine.setProperty('voice', matching[0].id)
    elif language != 'en':
        raise RuntimeError('Install an operating-system voice for this language')
    engine.setProperty('rate', round(155*float(sys.argv[3] if len(sys.argv)>3 else 1)))
    engine.setProperty('volume', min(1, max(.1, float(sys.argv[4] if len(sys.argv)>4 else 1))))
    text=sys.stdin.read()
    path=Path(sys.argv[1]);timing=path.with_suffix('.words.json')
    if os.name=='nt':
        # pyttsx3 queues voice/rate/volume changes until its command loop runs.
        # Apply those commands before copying settings to timed SAPI.
        engine.runAndWait()
        driver=engine.proxy._driver
        payload={'text':text,'voice_name':next(v.name for v in voices if v.id==engine.getProperty('voice')),'rate':driver._tts.Rate,'volume':driver._tts.Volume,'path':str(path),'timing_path':str(timing)}
        engine.stop()
        subprocess.run(['powershell.exe','-NoProfile','-File',str(Path(__file__).with_name('sapi_timing.ps1'))],input=json.dumps(payload),encoding='utf8',capture_output=True,check=True,timeout=65)
        data=json.loads(timing.read_text(encoding='utf-8-sig'))
        with wave.open(str(path),'rb') as audio:
            duration=audio.getnframes()/audio.getframerate()
            pcm_hash=hashlib.sha256(audio.readframes(audio.getnframes())).hexdigest()
        data.update(provider='Windows SAPI native synthesis word boundaries',script_sha256=hashlib.sha256(text.encode()).hexdigest(),audio_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pcm_sha256=pcm_hash,duration=duration)
        for row in data['words']:row['char']=row.pop('character')
        timing.write_text(json.dumps(data,indent=2),encoding='utf8')
    else:
        engine.save_to_file(text,str(path));engine.runAndWait();engine.stop()

if __name__ == '__main__':
    main()
