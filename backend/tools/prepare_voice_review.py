"""Loudness-match auditions without changing pace, pitch or pauses."""
import json,subprocess,hashlib,wave
from pathlib import Path
from app.core.config import settings
from app.video.final_audio import parse_loudness
BASE=Path(__file__).resolve().parents[2]/'generated/hybrid-review'
rows=json.loads((BASE/'final-voice-comparison.json').read_text());reports=[]
for row in rows:
 if row['exit']:raise RuntimeError('Failed audition must not be presented as valid')
 source=Path(row['path']);out=source.with_name(source.stem+'-listen.wav')
 target='I=-16:TP=-2:LRA=9'
 def run(args):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=60)
 measure=parse_loudness(run([settings.ffmpeg_path,'-hide_banner','-i',str(source),'-af','loudnorm='+target+':print_format=json','-f','null','-']).stderr)
 filter='loudnorm='+target+f":measured_I={measure['input_i']}:measured_TP={measure['input_tp']}:measured_LRA={measure['input_lra']}:measured_thresh={measure['input_thresh']}:offset={measure['target_offset']}:linear=true,alimiter=limit=.79:level=0:latency=1,aresample=48000"
 run([settings.ffmpeg_path,'-y','-v','error','-i',str(source),'-af',filter,'-c:a','pcm_s16le',str(out)])
 with wave.open(str(source)) as w:before=w.getnframes()/w.getframerate()
 with wave.open(str(out)) as w:after=w.getnframes()/w.getframerate()
 if abs(before-after)>.002:raise ValueError('Audition processing changed time')
 actual=parse_loudness(run([settings.ffmpeg_path,'-hide_banner','-i',str(out),'-af','loudnorm='+target+':print_format=json','-f','null','-']).stderr)
 generation=json.loads(source.with_suffix('.generation.json').read_text()) if source.with_suffix('.generation.json').exists() else None
 reports.append({**row,'listen_path':str(out),'duration':after,'generation':generation,'loudness':actual,'time_unchanged':True,'processing':'measured loudness/peak management only; raw WAV retained','sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
(BASE/'voice-review-results.json').write_text(json.dumps(reports,indent=2));print('Prepared',len(reports),'playable matched-level auditions',flush=True)
