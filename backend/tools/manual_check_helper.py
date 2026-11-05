"""Manual-check helper: report Google OAuth configuration and write short narration samples.

Run from the backend folder:  ../.venv/Scripts/python.exe tools/manual_check_helper.py
Secrets are never printed; only 'configured' / 'MISSING' is shown. Samples go to
generated/listening_review/ (git-ignored private output, excluded from the handover archive).
Only narration adapters that are already configured are used; paid cloud adapters are
called once each for a single ~3 second sentence.
"""
import sys,wave
from pathlib import Path

BACKEND=Path(__file__).resolve().parents[1]
ROOT=BACKEND.parent
sys.path.insert(0,str(BACKEND))

SAMPLE_TEXT='This is a short narration sample for listening review.'
KOKORO_PRESET='bm_george'


def read_env(path):
    values={}
    if path.is_file():
        for line in path.read_text(encoding='utf8').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                key,value=line.split('=',1);values[key.strip()]=value.strip().strip('"\'')
    return values


def check_oauth():
    env_path=BACKEND/'.env'
    print('== Google OAuth (backend/.env) ==')
    if not env_path.is_file():
        print('  backend/.env not found. Copy backend/.env.example to backend/.env first.')
    env=read_env(env_path)
    ready=True
    for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REDIRECT_URI'):
        value=env.get(key,'')
        if value:
            shown=value if key=='GOOGLE_REDIRECT_URI' else 'configured'
            print(f'  {key:<22} {shown}')
        else:
            ready=False;print(f'  {key:<22} MISSING')
    redirect=env.get('GOOGLE_REDIRECT_URI','')
    if redirect and not redirect.endswith('/api/youtube/callback'):
        print('  note: redirect URI should end with /api/youtube/callback and match the Google Cloud console exactly')
    print('  Result:',
          'OAuth settings present (consent and channel identity still need a manual check).' if ready
          else 'OAuth NOT ready. See GOOGLE_OAUTH_SETUP.md.')


def duration(path):
    try:
        with wave.open(str(path),'rb') as audio:return audio.getnframes()/audio.getframerate()
    except Exception:return None


def make_samples():
    print('\n== Narration samples ==')
    from app.tts.capabilities import configured
    from app.tts.providers import generate_narration
    out=ROOT/'generated'/'listening_review';out.mkdir(parents=True,exist_ok=True)
    print('  Output folder:',out)
    for provider,voice in (('local',''),('kokoro_onnx',KOKORO_PRESET),('google',''),('elevenlabs','')):
        if not configured(provider):
            print(f'  {provider:<12} not configured - skipped');continue
        path=out/f'{provider}.wav'
        try:
            metadata={}
            label=generate_narration(SAMPLE_TEXT,voice,path,provider=provider,language='en-US',metadata=metadata)
            seconds=duration(path)
            detail=f'{seconds:.1f}s' if seconds else 'written'
            print(f'  {provider:<12} OK ({detail}) voice={metadata.get("voice","?")} -> {path.name} [{label}]')
        except Exception as exc:
            print(f'  {provider:<12} FAILED: {type(exc).__name__}: {str(exc)[:200]}')


def main():
    check_oauth();make_samples()
    print('\nListen to the files above, then record your pronunciation/naturalness/sync verdict.')


if __name__=='__main__':main()
