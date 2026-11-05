import json,subprocess,hashlib,re,array,wave
from pathlib import Path
from PIL import Image,ImageDraw
from app.database.session import SessionLocal
from app.models import TitleShortDraft
from app.core.config import settings
from app.video.alignment import load_boundaries
from app.video.final_audio import parse_loudness
OUT=Path('../generated/super-bowl-script/render-licensed').resolve();id=(OUT/'draft-id.txt').read_text().strip()
def run(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=180);return {'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
def sec(t):
 h,m,s=t.split(':');return int(h)*3600+int(m)*60+float(s)
with SessionLocal() as db:
 d=db.get(TitleShortDraft,id);data=json.loads(d.data);assert d.status=='ready',d.error_message;video=Path(data['video']['path']);script=' '.join(s['narration'] for s in data['plan']['scenes']);voice=data['voice']
probe=json.loads(run([settings.ffprobe_path,'-v','error','-show_format','-show_streams','-of','json',str(video)])['stdout'])
result={'id':id,'video':str(video),'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'voice':voice,'probe':probe,'direct_listening':False}
for name,p in [('render',video),('exact_browser_download',OUT/'acceptance-download.mp4')]:result[name+'_decode']=run([settings.ffmpeg_path,'-v','error','-xerror','-i',str(p),'-f','null','-'])
result['download_hash_matches']=hashlib.sha256((OUT/'acceptance-download.mp4').read_bytes()).hexdigest()==result['sha256']
result['audio_loudness']=parse_loudness(run([settings.ffmpeg_path,'-hide_banner','-i',str(video),'-vn','-af','loudnorm=I=-15:TP=-1.5:LRA=9:print_format=json','-f','null','-'])['stderr'])
pcm=subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(video),'-vn','-acodec','pcm_s16le','-f','s16le','-'],capture_output=True,check=True,timeout=60).stdout;samples=array.array('h');samples.frombytes(pcm);result['clipped_pcm_samples']=sum(abs(v)>=32767 for v in samples)
for key,filter in [('black','blackdetect=d=0.05:pix_th=0.02'),('freeze','freezedetect=n=-60dB:d=0.7')]:result[key]=run([settings.ffmpeg_path,'-hide_banner','-i',str(video),'-an','-vf',filter,'-f','null','-'])
timing=load_boundaries(video.parent/'narration.wav',script);assert timing
ass=(video.parent/'captions.ass').read_text();cues=[];cursor=0
for line in ass.splitlines():
 if not line.startswith('Dialogue:'):continue
 z=line.split(',',9);text=z[-1].replace('\\N',' ');at=script.find(text,cursor);assert at>=0
 first_end=at+len(text.split()[0]);native=min(w['start'] for w in timing['words'] if w['char']<first_end and w['char']+w['length']>at)
 cues.append({'start':sec(z[1]),'end':sec(z[2]),'text':text,'native_start':native});cursor=at+len(text)
result['captions']={'count':len(cues),'script_words_exact':' '.join(x['text'] for x in cues).split()==script.split(),'nonoverlapping':all(a['end']<=b['start'] for a,b in zip(cues,cues[1:])),'within_audio':all(0<=x['start']<x['end']<=timing['duration']+.01 for x in cues),'maximum_native_start_delta':max(abs(x['start']-x['native_start']) for x in cues),'max_lines':max(len(l.split(',',9)[-1].split('\\N')) for l in ass.splitlines() if l.startswith('Dialogue:')),'timing_method':timing['provider']}
result['native_timing_audio_script_hash_valid']=True;result['source_count']=len(data['sources']);result['asset_count']=len(data['assets']);result['distinct_photo_hashes']=len({a['hash'] for a in data['assets']});result['source_urls']=[s['url'] for s in data['sources']]
timeline=json.loads((video.parent/'render-timeline.json').read_text());dur=float(probe['format']['duration'])
def frame(t,name):
 file=OUT/(name+'.jpg');r=run([settings.ffmpeg_path,'-y','-v','error','-ss',str(max(0,min(t,dur-.05))),'-i',str(video),'-frames:v','1',str(file)]);assert r['exit']==0;return Image.open(file).convert('RGB')
sheet=Image.new('RGB',(720,len(timeline['scenes'])*450),'#171717');draw=ImageDraw.Draw(sheet)
for i,s in enumerate(timeline['scenes']):
 for j,t in enumerate([s['start']+.1,(s['start']+s['end'])/2,s['end']-.1]):
  im=frame(t,f'scene-{i+1}-{j}');im.thumbnail((240,426));sheet.paste(im,(j*240,i*450+24));draw.text((j*240+3,i*450+4),f'Scene {i+1} {t:.2f}s',fill='white')
sheet.save(OUT/'scene-contact-sheet.jpg')
sheet=Image.new('RGB',(720,len(timeline['transitions'])*450),'#171717');draw=ImageDraw.Draw(sheet)
for i,s in enumerate(timeline['transitions']):
 for j,t in enumerate([s['offset']-.06,s['offset']+s['duration']/2,s['offset']+s['duration']+.06]):
  im=frame(t,f'transition-{i+1}-{j}');im.thumbnail((240,426));sheet.paste(im,(j*240,i*450+24));draw.text((j*240+3,i*450+4),f'{s["type"]} {t:.2f}s',fill='white')
sheet.save(OUT/'transition-contact-sheet.jpg')
sheet=Image.new('RGB',(720,((len(cues)+2)//3)*450),'#171717');draw=ImageDraw.Draw(sheet)
for i,c in enumerate(cues):
 im=frame((c['start']+c['end'])/2,f'caption-{i+1}');im.thumbnail((240,426));x=(i%3)*240;y=(i//3)*450;sheet.paste(im,(x,y+24));draw.text((x+3,y+4),f'Cue {i+1}: {c["start"]:.2f}s',fill='white')
sheet.save(OUT/'caption-contact-sheet.jpg')
video_stream=next(s for s in probe['streams'] if s['codec_type']=='video');audio_stream=next(s for s in probe['streams'] if s['codec_type']=='audio')
result['objective_checks_passed']=all([result['render_decode']['exit']==0,not result['render_decode']['stderr'],result['exact_browser_download_decode']['exit']==0,result['download_hash_matches'],not result['clipped_pcm_samples'],result['black']['exit']==0,result['freeze']['exit']==0,not re.search('black_start:',result['black']['stderr']),not re.search('freeze_start:',result['freeze']['stderr']),result['captions']['script_words_exact'],result['captions']['nonoverlapping'],result['captions']['within_audio'],result['captions']['maximum_native_start_delta']<=.011,video_stream['width']==1080,video_stream['height']==1920,video_stream['avg_frame_rate']=='30/1',audio_stream['sample_rate']=='48000',result['distinct_photo_hashes']==3])
(OUT/'technical-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:result[k] for k in ['video','sha256','audio_loudness','clipped_pcm_samples','captions','objective_checks_passed']},indent=2))
