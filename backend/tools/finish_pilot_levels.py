"""New immutable revisions; copy verified video, change only narration gain."""
import os,json,hashlib,shutil,subprocess
from pathlib import Path
os.environ['YOUTUBE_UPLOADS_ENABLED']='false'
os.environ['SCHEDULER_ENABLED']='false'
from app.database.session import SessionLocal
from app.models import VideoJob
from app.core.config import settings
from app.services.preferences import invalidate_approvals
from app.video.final_audio import finalize_narration
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'generated/quality-revision/clean-pilots'
for subject in ['Henry','Ronaldo','Messi']:
 candidate=BASE/(subject.lower()+'-candidate.json');info=json.loads(candidate.read_text())
 with SessionLocal() as db:
  job=db.get(VideoJob,info['job_id']);assert job.status=='ready_for_review'
  old=Path(job.video.output_path);old_duration=job.video.duration
  invalidate_approvals(db,job);job.media_revision+=1
  folder=old.parent.parent/('revision-'+str(job.content_revision));assert not folder.exists();folder.mkdir()
  for name in ['captions.ass','render-timeline.json','subtitle-timing.json','media-manifest.json','render-command.json','poster.jpg']:
   shutil.copy2(old.parent/name,folder/name)
  shutil.copytree(old.parent/'fonts',folder/'fonts')
  audio,timing,report=finalize_narration(old.parent/'narration.wav',job.script.full_script,folder)
  previous=json.loads((old.parent/'audio-processing.json').read_text())
  assert abs(report['finished_audio_duration']-previous['finished_audio_duration'])<.001 and not report['removed_intervals'],'Timing changed; use full renderer'
  out=folder/'short.mp4'
  command=[settings.ffmpeg_path,'-y','-v','error','-i',str(old),'-i',str(audio),'-map','0:v:0','-map','1:a:0','-c:v','copy','-af','apad','-t',str(old_duration),'-c:a','aac','-ar','48000','-b:a','160k','-movflags','+faststart',str(out)]
  subprocess.run(command,check=True,capture_output=True,timeout=120)
  (folder/'remux-command.json').write_text(json.dumps(command,indent=2))
  (folder/'video-inheritance.json').write_text(json.dumps({'source':str(old),'operation':'video stream copy; caption pixels, scene timing, transitions unchanged; narration level corrected without speed change'},indent=2))
  subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(out),'-f','null','-'],capture_output=True,check=True,timeout=120)
  timing_report=json.loads((folder/'subtitle-timing.json').read_text());timing_report['source_audio_sha256']=timing['audio_sha256'];(folder/'subtitle-timing.json').write_text(json.dumps(timing_report,indent=2))
  job.video.output_path=str(out);job.video.media_revision=job.media_revision
  voice=ROOT/'generated/audio'/(job.id+'.wav');shutil.copy2(audio,voice);shutil.copy2(audio.with_suffix('.words.json'),voice.with_suffix('.words.json'));job.voice_generation.output_path=str(voice)
  shutil.copy2(out,out.parent.parent/'short.mp4');db.commit()
  info.update(revision=job.content_revision,media_revision=job.media_revision,mp4_path=str(out),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),audio_processing=report,voice_name=job.voice_generation.voice)
  candidate.write_text(json.dumps(info,indent=2));print(subject,job.content_revision,str(out),flush=True)
