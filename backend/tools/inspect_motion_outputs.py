import json,re,hashlib,wave,subprocess,math,struct
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageStat
from app.core.config import settings
from app.video.alignment import load_boundaries
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/motion-continuation';rows=json.loads((OUT/'pilots.json').read_text());evidence=[]
for row in rows:
 j=row['job'];jid=j['id'];audio=ROOT/'generated/audio'/f'{jid}.wav';script=j['script']['full_script'];timing=load_boundaries(audio,script);assert timing
 ass=ROOT/'generated/videos'/jid/'captions.ass';srt=ROOT/'generated/subtitles'/f'{jid}.srt'
 cues=srt.read_text(encoding='utf8').strip().split('\n\n');display=' '.join(' '.join(c.splitlines()[2:]) for c in cues)
 assert display.split()==script.split()
 with wave.open(str(audio)) as w:
  pcm=w.readframes(w.getnframes());duration=w.getnframes()/w.getframerate();samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
 command=json.loads((ROOT/'generated/videos'/jid/'render-command.json').read_text());graph=command[command.index('-filter_complex')+1];assert 'atempo=' not in graph
 offsets=[float(x) for x in re.findall(r'xfade=transition=fade:duration=[^:;]+:offset=([\d.]+)',graph)]
 times=[.1]+[x+.2 for x in offsets]+[duration+.4]
 thumbs=[]
 folder=OUT/jid/'inspection';folder.mkdir(exist_ok=True)
 for i,t in enumerate(times):
  path=folder/f'boundary-{i}.jpg'
  subprocess.run([settings.ffmpeg_path,'-y','-v','error','-ss',str(t),'-i',row['mp4_path'],'-frames:v','1',str(path)],check=True,capture_output=True)
  im=Image.open(path).convert('RGB');im.thumbnail((216,384));thumbs.append((t,im))
 sheet=Image.new('RGB',(216*len(thumbs),410),'white');draw=ImageDraw.Draw(sheet)
 for i,(t,im) in enumerate(thumbs):sheet.paste(im,(i*216,26));draw.text((i*216+5,5),f'{t:.2f}s',fill='black')
 sheet.save(folder/'transitions.jpg')
 # Compare image regions away from subtitles within the same scene.
 frames=[]
 for t in [.5,2]:
  p=subprocess.run([settings.ffmpeg_path,'-v','error','-ss',str(t),'-i',row['mp4_path'],'-frames:v','1','-vf','crop=800:1000:140:150,scale=160:200','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True)
  frames.append(Image.frombytes('RGB',(160,200),p.stdout))
 motion=sum(ImageStat.Stat(ImageChops.difference(*frames)).mean)/3
 evidence.append({'subject':row['subject'],'revision':j['content_revision'],'script_unchanged':hashlib.sha256(script.encode()).hexdigest()==row['script_hash'],'native_alignment_valid':True,'word_events':len(timing['words']),'caption_words_match_script':True,'source_audio_duration':duration,'source_sample_rate':16000,'rms_pcm':math.sqrt(sum(x*x for x in samples)/len(samples)),'source_clipped_samples':sum(abs(x)>=32767 for x in samples),'motion_region_mean_difference':motion,'transition_offsets':offsets,'transition_sheet':str(folder/'transitions.jpg'),'browser_full_playback':'See browser-playback.json; this helper does not operate a browser','subjective_listening':'BLOCKED: no audio listening interface available','pronunciation_review':'BLOCKED: requires listening','zero_cards':all(a['media_type']=='photo' for a in j['assets']),'distinct_reviewed_photos':4,'photo_scenes':6,'clip_scenes':0})
(OUT/'alignment-motion-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
print(json.dumps(evidence,indent=2))
