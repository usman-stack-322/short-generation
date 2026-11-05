import json,re,hashlib,subprocess,array,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from app.core.config import settings
ROOT=Path(__file__).resolve().parents[2]; BASE=ROOT/'generated/hybrid-review';OUT=BASE/'narration-caption-audit-20261028'
items=json.loads((BASE/'selected-revisions.json').read_text());rows=[]
def sec(s):
 h,m,s=s.split(':');return int(h)*3600+int(m)*60+float(s)
for item in items:
 p=Path(item['normal_mp4']);out=OUT/item['subject'].lower();a=json.loads((p.parent/'narration.words.json').read_text());ass=(p.parent/'captions.ass').read_text();cues=[];idx=0
 for line in ass.splitlines():
  if not line.startswith('Dialogue:'):continue
  z=line.split(',',9);text=z[9].replace('\\N',' ');count=len(text.split());words=a['words'][idx:idx+count];idx+=count
  cues.append({'start':sec(z[1]),'end':sec(z[2]),'text':text,'lines':z[9].split('\\N'),'native_first':words[0]['start'],'native_last_end':words[-1].get('end'),'start_delta':sec(z[1])-words[0]['start']})
 sheet=Image.new('RGB',(720,math.ceil(len(cues)/3)*450),'#171717');d=ImageDraw.Draw(sheet)
 for i,cue in enumerate(cues):
  t=(cue['start']+cue['end'])/2;file=out/f'caption-{i+1:02}.jpg'
  subprocess.run([settings.ffmpeg_path,'-y','-v','error','-ss',str(t),'-i',str(p),'-frames:v','1',str(file)],check=True,timeout=60)
  im=Image.open(file);im.thumbnail((240,426));x=(i%3)*240;y=(i//3)*450;sheet.paste(im,(x,y+24));d.text((x+4,y+5),f"{i+1}: {cue['start']:.2f}–{cue['end']:.2f}s",fill='white')
 sheet.save(out/'all-captions-contact-sheet.jpg')
 pcm=subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(p),'-vn','-acodec','pcm_s16le','-f','s16le','-'],capture_output=True,check=True,timeout=120).stdout
 values=array.array('h');values.frombytes(pcm)
 command=json.loads((p.parent/'render-command.json').read_text());inputs=[command[i+1] for i,v in enumerate(command[:-1]) if v=='-i']
 row={'subject':item['subject'],'revision':item['normal_revision'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'captions':cues,'cue_count':len(cues),'all_script_words_covered':idx==len(a['words']),'max_native_start_delta_seconds':max(abs(q['start_delta']) for q in cues),'max_lines':max(len(q['lines']) for q in cues),'duplicate_intervals':len(cues)-len({(q['start'],q['end']) for q in cues}),'minimum_cue_seconds':min(q['end']-q['start'] for q in cues),'decoded_mp4_clipped_samples':sum(abs(v)>=32767 for v in values),'decoded_mp4_peak':max(abs(v) for v in values),'narration_duration':a['duration'],'last_native_word_end':a['words'][-1].get('end'),'audio_inputs':[s for s in inputs if s.endswith('.wav')],'has_amix':any('amix' in s for s in command)}
 rows.append(row)
(OUT/'caption-audio-detail.json').write_text(json.dumps(rows,indent=2));print(json.dumps([{k:v for k,v in x.items() if k!='captions'} for x in rows],indent=2))
