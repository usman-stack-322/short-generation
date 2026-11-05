"""Select verified local renders as new normal revisions, retaining old artifacts."""
import os,json,hashlib,shutil,subprocess
from pathlib import Path
os.environ['YOUTUBE_UPLOADS_ENABLED']='false';os.environ['SCHEDULER_ENABLED']='false'
from app.database.session import SessionLocal
from app.models import VideoJob,Asset,Scene,Thumbnail
from app.services.preferences import invalidate_approvals
from app.services.assets.credits import sync_credits
from app.core.config import settings
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'generated/hybrid-review'

def snapshot(record):
 return {c.name:getattr(record,c.name) for c in record.__table__.columns}

def main():
 selected=[]
 for subject in ['Ronaldo','Messi']:
  item=json.loads((BASE/('improved-'+subject.lower()+'-pilot.json')).read_text())
  data=json.loads(Path(item['scene_plan']).read_text());source=Path(item['mp4_path'])
  verification=json.loads((BASE/'verification'/subject.lower()/'results.json').read_text())
  if not verification['automated_checks_passed']:raise ValueError('Resolve verification failures first')
  generation=json.loads((Path(item['voice_plan']).parent/'source-narration.generation.json').read_text())
  henry=json.loads((BASE/'pilot-henry-revision-2/source-narration.generation.json').read_text())
  assert generation['model_sha256']==henry['model_sha256'] and generation['engine_controls']==henry['engine_controls']
  with SessionLocal() as db:
   job=db.get(VideoJob,data['original_job_id'])
   assert job.content_revision==data['original_revision'] and job.script.full_script==data['original_script']==item['script']
   assert job.status=='ready_for_review' and settings.youtube_uploads_enabled is False
   assets=db.query(Asset).filter_by(job_id=job.id).order_by(Asset.scene_number).all();scenes=db.query(Scene).filter_by(job_id=job.id).order_by(Scene.scene_number).all()
   old=Path(job.video.output_path);backup=BASE/'normal-before'/job.id/('revision-'+str(job.content_revision));backup.mkdir(parents=True,exist_ok=True)
   state={'job':snapshot(job),'voice':snapshot(job.voice_generation),'video':snapshot(job.video),'scenes':[snapshot(s) for s in scenes],'assets':[snapshot(a) for a in assets],'script':job.script.full_script,'mp4_sha256':hashlib.sha256(old.read_bytes()).hexdigest()}
   (backup/'state.json').write_text(json.dumps(state,indent=2,default=str))
   for p in [old,Path(job.voice_generation.output_path),ROOT/'generated/subtitles'/(job.id+'.srt')]:
    if p.is_file() and not (backup/p.name).exists():shutil.copy2(p,backup/p.name)
   invalidate_approvals(db,job);job.media_revision+=1
   destination=ROOT/'generated/videos'/job.id/('revision-'+str(job.content_revision))
   if destination.exists():
    assert hashlib.sha256((destination/'short.mp4').read_bytes()).hexdigest()==item['sha256'],'Existing revision differs; do not overwrite'
   else:shutil.copytree(source.parent,destination)
   timeline=json.loads((destination/'render-timeline.json').read_text());chosen=[]
   for i,(plan,span) in enumerate(zip(data['scenes'],timeline['scenes'])):
    asset=next(a for a in assets if a.url==plan['source_url'] and a not in chosen);chosen.append(asset)
    meta=json.loads(asset.provenance or '{}');meta.update(focal_x=.5,focal_y=.18,scene_motion=plan['motion'],modifications='Native-detail proportional framing, same-photo backdrop and planned restrained motion; box-free captions')
    asset.scene_number=i+1;asset.provenance=json.dumps(meta)
    scene=scenes[i];scene.scene_number=i+1;scene.start_time=span['start'];scene.end_time=span['end'];scene.narration=plan['text'];scene.caption=' '.join(plan['text'].split()[:5]);scene.visual_type='photo'
   for asset in assets:
    if asset not in chosen:db.delete(asset)
   for scene in scenes[len(data['scenes']):]:db.delete(scene)
   voice=job.voice_generation;voice.provider='Kokoro local narrator';voice.voice='bm_george';voice.speed=1.;voice.script_hash=item['script_sha256'];voice.output_path=str(destination/'narration.wav')
   voice.voice_profile=json.dumps({'style':'documentary','tone':'natural measured','pace':1.,'energy':.5,'pitch':0.,'volume':1.,'emotion':'editorial target only','pause_strength':.5,'emphasis_strength':.5,'auto_selected':False,'reason':'User selected the exact accepted Henry review narrator','language_code':'en-US','locale':'en-GB'})
   voice.delivery=json.dumps({'provider':'kokoro_onnx','voice':'bm_george','model':generation['model'],'locale':'en-GB','controls':generation['engine_controls'],'audio_available':True,'source_script_sha256':item['script_sha256'],'model_sha256':generation['model_sha256'],'naturalness_verified':False})
   job.voice='bm_george';job.tts_provider='kokoro_onnx';job.voice_style='documentary'
   if float(verification['probe']['format']['duration'])>job.duration:job.duration=45
   trace=json.loads(job.research_trace or '{}');trace['accepted_henry_scene_plan']=data['scenes'];trace['accepted_voice_reference']='Henry local review v2 / Kokoro bm_george';job.research_trace=json.dumps(trace)
   job.video.thumbnail_path=str(destination/'poster.jpg')
   thumbnail=db.query(Thumbnail).filter_by(job_id=job.id).first()
   if thumbnail:thumbnail.local_path=str(destination/'poster.jpg')
   job.video.output_path=str(destination/'short.mp4');job.video.duration=float(verification['probe']['format']['duration']);job.video.media_revision=job.media_revision;job.video.status='ready_for_review'
   job.status=job.current_step='ready_for_review';job.error_message=job.failed_step=None
   warnings=[w for w in json.loads(job.warnings or '[]') if not w.startswith('Quality review pending:')]
   warnings.append('Quality review pending: new Kokoro bm_george narration; listening, names and perceptual caption synchronization require final user review.');job.warnings=json.dumps(warnings)
   db.flush();sync_credits(db,job);db.commit()
   # Versioned output is canonical. Refresh compatibility mirrors after commit.
   shutil.copy2(destination/'short.mp4',destination.parent/'short.mp4')
   for name in ['narration.wav','narration.words.json']:
    shutil.copy2(destination/name,ROOT/'generated/audio'/(job.id+('.wav' if name.endswith('.wav') else '.words.json')))
   shutil.copy2(BASE/'pilot/subtitles'/(subject.lower()+'-local-review.srt'),ROOT/'generated/subtitles'/(job.id+'.srt'))
   row={**item,'normal_job_id':job.id,'normal_revision':job.content_revision,'normal_mp4':str(destination/'short.mp4'),'script_unchanged':job.script.full_script==data['original_script'],'previous_mp4_preserved':old.is_file(),'previous_sha256_matches':hashlib.sha256(old.read_bytes()).hexdigest()==state['mp4_sha256'],'selected_sha256_matches':hashlib.sha256((destination/'short.mp4').read_bytes()).hexdigest()==item['sha256']}
   selected.append(row);print(subject,job.content_revision,str(destination/'short.mp4'),flush=True)
 (BASE/'selected-revisions.json').write_text(json.dumps(selected,indent=2))
if __name__=='__main__':main()
