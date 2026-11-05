import json
from pathlib import Path
from app.database.session import SessionLocal
from app.models import TitleShortDraft
from app.services.title_shorts import narrator_choice
from app.tts.providers import generate_narration
from app.video.renderer import audio_duration,validate_narration
from app.video.alignment import load_boundaries
p=Path('../generated/super-bowl-script/fixed-native-voice');p.mkdir(exist_ok=True)
with SessionLocal() as db:d=db.get(TitleShortDraft,'83aed818-f7ff-489f-80fc-4573f844d628');data=json.loads(d.data)
text=' '.join(s['narration'] for s in data['plan']['scenes']);provider,voice=narrator_choice('English','local');meta={};audio=p/'source.wav'
generate_narration(text,voice,audio,provider=provider,language='en-US',metadata=meta);validate_narration(audio);duration=audio_duration(audio)
result={'duration':duration,'voice':meta,'native_boundaries_valid':bool(load_boundaries(audio,text)),'within_budget':24<=duration<=29.3,'script':text};(p/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
