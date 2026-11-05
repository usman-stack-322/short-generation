"""Inspect exact selected MP4 bytes, final-audio alignment and private delivery."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from fractions import Fraction
import httpx
from PIL import Image,ImageDraw,ImageChops,ImageStat
from app.core.config import settings
from app.video.alignment import load_boundaries
from app.video.final_audio import parse_loudness

ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'generated/quality-revision/clean-pilots'
OLD={'Henry':18,'Ronaldo':17,'Messi':16}


def run(args,timeout=120):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    return {'exit':result.returncode,'stderr':result.stderr,'stdout':result.stdout}


def seconds(text):
    h,m,s=text.split(':');return int(h)*3600+int(m)*60+float(s.replace(',','.'))


def main(subject):
    candidate=json.loads((BASE/f'{subject.lower()}-candidate.json').read_text(encoding='utf8'))
    path=Path(candidate['mp4_path']);folder=BASE/'verification'/subject.lower();folder.mkdir(parents=True,exist_ok=True)
    probe=run([settings.ffprobe_path,'-v','error','-show_streams','-show_format','-of','json',str(path)])
    data=json.loads(probe['stdout']);video=next(s for s in data['streams'] if s['codec_type']=='video')
    duration=float(data['format']['duration']);timeline=json.loads((path.parent/'render-timeline.json').read_text())
    result={'subject':subject,'revision':candidate['revision'],'mp4_path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'probe':data,'duration':duration,'transitions':timeline['transitions'],'voice':candidate['voice_name'],
        'voice_id':candidate['voice'],'model':candidate['model'],'direct_listening':'NOT PERFORMED: no local audio listening interface'}
    result['decode']=run([settings.ffmpeg_path,'-v','error','-i',str(path),'-f','null','-'])
    result['blackdetect']=run([settings.ffmpeg_path,'-hide_banner','-i',str(path),'-an','-vf','blackdetect=d=0.05:pix_th=0.02','-f','null','-'])
    result['freezedetect']=run([settings.ffmpeg_path,'-hide_banner','-i',str(path),'-an','-vf','freezedetect=n=-60dB:d=0.7','-f','null','-'])
    loud=run([settings.ffmpeg_path,'-hide_banner','-i',str(path),'-vn','-af','loudnorm=I=-15:TP=-1.5:LRA=9:print_format=json','-f','null','-'])
    result['actual_audio']=parse_loudness(loud['stderr'])
    silence=run([settings.ffmpeg_path,'-hide_banner','-i',str(path),'-vn','-af','silencedetect=n=-42dB:d=0.25','-f','null','-'])
    result['silence_events']=re.findall(r'silence_(?:start|end|duration):\s*[-\d.]+',silence['stderr'])
    frames=run([settings.ffprobe_path,'-v','error','-select_streams','v','-show_entries','frame=best_effort_timestamp_time','-of','json',str(path)])
    timestamps=[float(f['best_effort_timestamp_time']) for f in json.loads(frames['stdout'])['frames']]
    result['timestamps']={'frames':len(timestamps),'strictly_increasing':all(b>a for a,b in zip(timestamps,timestamps[1:])),
        'maximum_step':max(b-a for a,b in zip(timestamps,timestamps[1:]))}
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=90) as client:
        login=client.post('/api/auth/login',json={'email':'owner@example.com','password':'DemoOwner123!'});login.raise_for_status()
        h={'Authorization':'Bearer '+login.json()['access_token']}
        job=client.get('/api/videos/'+candidate['job_id'],headers=h).json()
        assert job['content_revision']==candidate['revision'] and job['approval_count']==0
        download=client.get(job['video_url']+'&download=true',headers=h)
        download.raise_for_status()
        (folder/'download.mp4').write_bytes(download.content)
        result['download_decode']=run([settings.ffmpeg_path,'-v','error','-i',str(folder/'download.mp4'),'-f','null','-'])
        result['download']={'status':download.status_code,'sha256_matches':hashlib.sha256(download.content).hexdigest()==result['sha256'],
            'content_revision_header':download.headers.get('x-content-revision'),'cache_control':download.headers.get('cache-control')}
        result['preview_url']=job['video_url']
        result['anonymous_status']=httpx.get('http://127.0.0.1:8000'+job['video_url'],timeout=30).status_code
        seeking=client.get(job['video_url'],headers={**h,'Range':'bytes=10000-19999'})
        result['seeking']={'status':seeking.status_code,'content_range':seeking.headers.get('content-range')}
        voice=client.get(job['narration_url'],headers=h)
        result['narration_preview_matches_finished_audio']=hashlib.sha256(voice.content).hexdigest()==hashlib.sha256((path.parent/'narration.wav').read_bytes()).hexdigest()
    timing=load_boundaries(path.parent/'narration.wav',job['script']['full_script']);assert timing
    text=(ROOT/'generated/subtitles'/f"{candidate['job_id']}.srt").read_text(encoding='utf8')
    cues=text.strip().split('\n\n');display=' '.join(' '.join(c.splitlines()[2:]) for c in cues)
    spans=[tuple(map(seconds,m)) for m in re.findall(r'(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})',text)]
    result['captions']={'native_timing_valid':True,'script_words_match':display.split()==job['script']['full_script'].split(),
        'nonoverlapping':all(spans[i][1]<=spans[i+1][0]+.001 for i in range(len(spans)-1)),
        'inside_final_audio':all(0<=a<b<=timing['duration']+.001 for a,b in spans),
        'cross_scene_cues':[(a,b) for a,b in spans for c in timeline['transitions'] if a<c['at']-.003 and b>c['at']+.003],
        'word_counts':[len(' '.join(c.splitlines()[2:]).split()) for c in cues],
        'last_caption':cues[-1].splitlines()[-1],'perceived_150ms_sync':'UNVERIFIED: requires listening'}
    command=json.loads((path.parent/'render-command.json').read_text());graph=command[command.index('-filter_complex')+1]
    result['no_renderer_label_or_panel']=all(x not in graph for x in ('drawtext=','drawbox=','editorial-scrim'))
    def image_at(t,label,source=path):
        target=folder/(label+'.jpg')
        r=run([settings.ffmpeg_path,'-y','-v','error','-ss',f'{max(0,min(t,duration-.05)):.6f}','-i',str(source),'-frames:v','1',str(target)])
        if r['exit']!=0 or not target.is_file():raise RuntimeError('Frame extraction failed: '+r['stderr'])
        return Image.open(target).convert('RGB')
    sheet=Image.new('RGB',(720,6*450),'#171717');draw=ImageDraw.Draw(sheet);motion=[]
    for i,span in enumerate(timeline['scenes']):
        start=max(span['start']+.08,timeline['transitions'][i-1]['offset']+timeline['transitions'][i-1]['duration']+.05 if i else .08)
        end=min(span['end']-.08,timeline['transitions'][i]['offset']-.05 if i<len(timeline['transitions']) else duration-.08)
        times=[start,(start+end)/2,end];full=[]
        for j,t in enumerate(times):
            im=image_at(t,f'scene-{i+1}-{j}');full.append(im.copy());im.thumbnail((240,426));sheet.paste(im,(j*240,i*450+24))
            draw.text((j*240+5,i*450+5),f'Scene {i+1} {t:.2f}s',fill='white')
        difference=ImageChops.difference(full[0].crop((80,200,1000,1400)),full[-1].crop((80,200,1000,1400)))
        motion.append(sum(ImageStat.Stat(difference).mean)/3)
    sheet.save(folder/'motion-contact-sheet.jpg');result['motion_region_difference']=motion
    transitions=Image.new('RGB',(720,len(timeline['transitions'])*450),'#171717');draw=ImageDraw.Draw(transitions)
    for i,c in enumerate(timeline['transitions']):
        for j,t in enumerate([c['offset']-.06,c['offset']+c['duration']/2,c['offset']+c['duration']+.06]):
            im=image_at(t,f'transition-{i+1}-{j}');im.thumbnail((240,426));transitions.paste(im,(j*240,i*450+24))
            draw.text((j*240+5,i*450+5),f"{c['type']} {t:.3f}s",fill='white')
    transitions.save(folder/'transition-contact-sheet.jpg')
    old=ROOT/'generated/motion-continuation'/candidate['job_id']/f'revision-{OLD[subject]}'/'short.mp4'
    before=image_at(.15,'before-opening',old);after=image_at(.15,'after-opening')
    comparison=Image.new('RGB',(720,670),'#171717');draw=ImageDraw.Draw(comparison)
    for i,(label,im) in enumerate([('Rejected output',before),('New output',after)]):
        im.thumbnail((360,640));comparison.paste(im,(i*360,30));draw.text((i*360+10,8),label,fill='white')
    comparison.save(folder/'before-after.jpg')
    result['automated_checks_passed']=bool(result['decode']['exit']==0 and result['download']['sha256_matches']
        and result['anonymous_status']==401 and result['seeking']['status']==206 and result['narration_preview_matches_finished_audio']
        and result['no_renderer_label_or_panel'] and result['captions']['script_words_match'] and result['captions']['inside_final_audio']
        and result['captions']['nonoverlapping'] and not result['captions']['cross_scene_cues']
        and result['timestamps']['strictly_increasing'] and abs(Fraction(video['avg_frame_rate'])-30)<.001
        and not re.search(r'black_start:',result['blackdetect']['stderr'])
        and not re.search(r'freeze_start:',result['freezedetect']['stderr'])
        and -16<=float(result['actual_audio']['input_i'])<=-14 and float(result['actual_audio']['input_tp'])<=-1)
    result['visual_inspection']='Pending contact-sheet/browser inspection';result['browser_playback']='Pending'
    (folder/'results.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({'subject':subject,'revision':candidate['revision'],'duration':duration,
        'actual_LUFS':result['actual_audio']['input_i'],'true_peak_dBTP':result['actual_audio']['input_tp'],
        'automated_checks_passed':result['automated_checks_passed'],'motion':motion,'folder':str(folder)},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--subject',choices=OLD,default='Henry');main(parser.parse_args().subject)
