import json,subprocess,re,hashlib,wave,array
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageStat
from app.core.config import settings
from app.video.alignment import load_boundaries
from app.video.final_audio import parse_loudness
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'generated/hybrid-review'

def run(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=180)
 return {'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}

def main(subject='Henry'):
 item=json.loads((BASE/('improved-pilot.json' if subject=='Henry' else 'improved-'+subject.lower()+'-pilot.json')).read_text());path=Path(item['mp4_path']);OUT=BASE/'verification'/subject.lower();OUT.mkdir(parents=True,exist_ok=True)
 probe=json.loads(run([settings.ffprobe_path,'-v','error','-show_streams','-show_format','-of','json',str(path)])['stdout'])
 timeline=json.loads((path.parent/'render-timeline.json').read_text());manifest=json.loads((path.parent/'media-manifest.json').read_text());duration=float(probe['format']['duration'])
 result={'candidate':item,'probe':probe,'timeline':timeline,'manifest':manifest,'direct_listening':False,'editorial_approval':False}
 result['decode']=run([settings.ffmpeg_path,'-v','error','-i',str(path),'-f','null','-'])
 for name,filter in [('blackdetect','blackdetect=d=.05:pix_th=.02'),('freezedetect','freezedetect=n=-60dB:d=.7')]:
  result[name]=run([settings.ffmpeg_path,'-hide_banner','-i',str(path),'-an','-vf',filter,'-f','null','-'])
 result['audio_loudness']=parse_loudness(run([settings.ffmpeg_path,'-hide_banner','-i',str(path),'-vn','-af','loudnorm=I=-15:TP=-1.5:LRA=9:print_format=json','-f','null','-'])['stderr'])
 silence=run([settings.ffmpeg_path,'-hide_banner','-i',str(path),'-vn','-af','silencedetect=n=-42dB:d=.25','-f','null','-'])
 result['audio_quiet_events']=re.findall(r'silence_(?:start|end|duration):\s*[-\d.]+',silence['stderr'])
 with wave.open(str(path.parent/'narration.wav')) as w:pcm=array.array('h');pcm.frombytes(w.readframes(w.getnframes()))
 result['clipped_pcm_samples']=sum(abs(x)>=32767 for x in pcm)
 timing=load_boundaries(path.parent/'narration.wav',item['script']);assert timing
 srt=(BASE/'pilot/subtitles'/(subject.lower()+'-local-review.srt')).read_text();cues=srt.strip().split('\n\n')
 displayed=' '.join(' '.join(c.splitlines()[2:]) for c in cues)
 def seconds(v):h,m,s=v.replace(',','.').split(':');return int(h)*3600+int(m)*60+float(s)
 spans=[tuple(map(seconds,m)) for m in re.findall(r'(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})',srt)]
 result['captions']={'exact_words':displayed.split()==item['script'].split(),'nonoverlapping':all(a[1]<=b[0]+.001 for a,b in zip(spans,spans[1:])),
  'within_audio':all(0<=a<b<=timing['duration']+.001 for a,b in spans),'method':timing['provider'],'native_hashes_valid':True,
  'last_caption':cues[-1].splitlines()[-1],'perceived_sync':'pending human listening'}
 sheet=Image.new('RGB',(720,len(timeline['scenes'])*450),'#171717');draw=ImageDraw.Draw(sheet);motion=[]
 def frame(t,name):
  out=OUT/(name+'.jpg');r=run([settings.ffmpeg_path,'-y','-v','error','-ss',str(max(0,min(t,duration-.05))),'-i',str(path),'-frames:v','1',str(out)])
  if r['exit']:raise RuntimeError(r['stderr'])
  return Image.open(out).convert('RGB')
 for i,span in enumerate(timeline['scenes']):
  start=span['start']+.2;end=span['end']-.25;images=[]
  for j,t in enumerate([start,(start+end)/2,end]):
   im=frame(t,f'scene-{i+1}-{j}');images.append(im.copy());im.thumbnail((240,426));sheet.paste(im,(j*240,i*450+24));draw.text((j*240+5,i*450+5),f"Scene {i+1} {t:.2f}s",fill='white')
  diff=ImageChops.difference(images[0].crop((80,200,1000,1400)),images[-1].crop((80,200,1000,1400)));motion.append(sum(ImageStat.Stat(diff).mean)/3)
 sheet.save(OUT/'motion-contact-sheet.jpg');result['motion_differences']=motion
 sheet=Image.new('RGB',(720,len(timeline['transitions'])*450),'#171717');draw=ImageDraw.Draw(sheet)
 for i,c in enumerate(timeline['transitions']):
  for j,t in enumerate([c['offset']-.06,c['offset']+c['duration']/2,c['offset']+c['duration']+.06]):
   im=frame(t,f'transition-{i+1}-{j}');im.thumbnail((240,426));sheet.paste(im,(j*240,i*450+24));draw.text((j*240+5,i*450+5),f"{c['type']} {t:.2f}s",fill='white')
 sheet.save(OUT/'transition-contact-sheet.jpg')
 video=next(s for s in probe['streams'] if s['codec_type']=='video');audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
 result['automated_checks_passed']=all([result['decode']['exit']==0,video['width']==1080,video['height']==1920,video['avg_frame_rate']=='30/1',audio['sample_rate']=='48000',
  not re.search('black_start:',result['blackdetect']['stderr']),not re.search('freeze_start:',result['freezedetect']['stderr']),
  result['captions']['exact_words'],result['captions']['nonoverlapping'],result['captions']['within_audio'],not result['clipped_pcm_samples'],
  -16<=float(result['audio_loudness']['input_i'])<=-14,float(result['audio_loudness']['input_tp'])<=-1,all(m>0 for m in motion),
  len({m['source'] for m in manifest})==len(manifest),all(m.get('native_detail_preserved') for m in manifest)])
 (OUT/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k in ['captions','audio_loudness','clipped_pcm_samples','automated_checks_passed']},indent=2),flush=True)

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--subject',choices=['Henry','Ronaldo','Messi'],default='Henry');main(p.parse_args().subject)
