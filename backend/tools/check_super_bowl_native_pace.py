import json
from pathlib import Path
from app.services.title_shorts import narrator_choice
from app.tts.providers import generate_narration
from app.video.renderer import audio_duration,validate_narration
from app.video.alignment import load_boundaries
folder=Path('../generated/super-bowl-script');lines=json.loads((folder/'timing-revision-lines.json').read_text());text=' '.join(lines);provider,voice=narrator_choice('English','local');p=folder/'native-pace-candidate'/'source.wav';meta={}
generate_narration(text,voice,p,provider=provider,language='en-US',metadata=meta,profile={'style':'educational','tone':'clear_patient','pace':0.96});validate_narration(p);duration=audio_duration(p);words=load_boundaries(p,text)
result={'provider':provider,'voice':voice,'metadata':meta,'duration':duration,'native_boundaries_valid':bool(words),'within_duration_budget':24<=duration<=29.3,'words':len(text.split())}
(folder/'timing-candidate'/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
