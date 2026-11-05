import json
from pathlib import Path
from app.video.renderer import audio_duration
p=Path('../generated/title-shorts/83aed818-f7ff-489f-80fc-4573f844d628/render-17/source.wav')
print(json.dumps({'audio_exists':p.is_file(),'duration':audio_duration(p) if p.is_file() else None}))
