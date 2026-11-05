"""Render one review pilot from a reusable explicit plan; no normal job overwrite."""
import argparse,json,subprocess,hashlib,sys,time
from pathlib import Path
from app.tts.scene_direction import narration_plan
from app.video.import_scene_plan import load_scene_assets
from app.video.renderer import render_video
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'generated/hybrid-review'
PYTHON=Path(r'C:/Users/ua589/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')

def main(path,voice,reuse=None):
    data,assets=load_scene_assets(path,ROOT)
    subject=data['subject'];job_id=subject.lower()+'-local-review'
    output_root=BASE/'pilot';folder=output_root/'videos'/job_id
    versions=[int(p.name.split('-')[-1]) for p in folder.glob('revision-*')] if folder.exists() else []
    versions += [int(p.name.split('-')[-1]) for p in BASE.glob('pilot-'+subject.lower()+'-revision-*')]
    revision=max(versions,default=0)+1
    candidate=BASE/('pilot-'+subject.lower()+'-revision-'+str(revision));candidate.mkdir(parents=True)
    plan=narration_plan(data['scenes'],voice,'kokoro_onnx')
    if data.get('original_script') is not None and data['original_script']!=plan['script']:
        raise ValueError('Scene segmentation changed the locked script')
    (candidate/'voice-plan.json').write_text(json.dumps(plan,indent=2));(candidate/'scene-plan.json').write_text(json.dumps(data,indent=2))
    audio=candidate/'source-narration.wav'
    payload={'runtime':str(BASE),'voice':voice,'text':plan['script'],'output':str(audio),'speed':1,'alignment_required':True}
    t=time.perf_counter()
    if reuse is not None:
        for suffix in ['.wav','.words.json','.generation.json','.phonemes.json']:
            source=Path(reuse).with_suffix(suffix);target=audio.with_suffix(suffix)
            if source.is_file():
                import shutil
                shutil.copy2(source,target)
        from app.video.alignment import load_boundaries
        if not load_boundaries(audio,plan['script']):raise ValueError('Cached narration does not match the locked script')
    else:
        result=subprocess.run([str(PYTHON),'-m','app.tts.kokoro_worker'],input=json.dumps(payload),encoding='utf8',capture_output=True,timeout=1200)
        (candidate/'synthesis-log.txt').write_text(result.stdout+'\n'+result.stderr)
        if result.returncode:raise RuntimeError(result.stderr[-2500:])
    output,_,_=render_video(job_id,subject+' award recognition',subject,plan['script'],audio,45,output_root,assets,
        scenes=None,subtitle_preset={'language':'en-US'},focal_positions=[tuple(s.get('focal',[.5,.18])) for s in data['scenes']],
        slide_kinds=[s['visual_type'] for s in data['scenes']],revision=revision,scene_plan=data['scenes'])
    credits='Archival photographs illustrate the player, not the historical award event.\nChanges: proportional framing, same-photo backdrop, planned camera motion, captions and transitions.\n\n'
    for i,s in enumerate(data['scenes'],1):
        if s['visual_type']=='ai_illustration':credits+=f"Scene {i}: AI illustration; "+json.dumps(s['generation'])+'\n'
        else:credits+=f"Scene {i}: {s['source_title']}\nPhoto by {s['creator']}\n{s['source_url']}\n{s['license']} {s.get('license_url','')}\nPhoto date: {s.get('capture_date','unknown')}\n\n"
    (output.parent/'credits.txt').write_text(credits,encoding='utf8')
    summary={'subject':subject,'revision':revision,'normal_job_revision_unchanged':data.get('original_revision'),'mp4_path':str(output),
             'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'script':plan['script'],'script_sha256':hashlib.sha256(plan['script'].encode()).hexdigest(),
             'voice':voice,'provider':'kokoro-onnx CPU','model':'Kokoro-82M v1.0 INT8','scene_plan':str(candidate/'scene-plan.json'),
             'voice_plan':str(candidate/'voice-plan.json'),'wall_seconds':time.perf_counter()-t,'photo_scenes':sum(s['visual_type']=='archival_photo' for s in data['scenes']),
             'clips':sum(s['visual_type']=='licensed_clip' for s in data['scenes']),'ai_scenes':sum(s['visual_type']=='ai_illustration' for s in data['scenes']),
             'paid_requests':0,'direct_listening':False,'editorial_approval':False}
    (BASE/('improved-'+subject.lower()+'-pilot.json')).write_text(json.dumps(summary,indent=2))
    if subject=='Henry':(BASE/'improved-pilot.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,default=BASE/'henry-scene-plan.json');p.add_argument('--voice',choices=['bm_george','bf_emma','am_michael'],default='bm_george');p.add_argument('--reuse-audio-from',type=Path);a=p.parse_args();main(a.plan,a.voice,a.reuse_audio_from)
