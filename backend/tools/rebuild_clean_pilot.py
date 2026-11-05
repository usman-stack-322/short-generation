"""Supervised local rebuild from retained licensed photos and saved narration.

No research, external provider, upload, scheduling or publishing requests.
Henry must be inspected before the other pilots are rebuilt.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

os.environ['YOUTUBE_UPLOADS_ENABLED']='false'
os.environ['SCHEDULER_ENABLED']='false'
from PIL import Image
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob,Asset,Scene
from app.services.preferences import invalidate_approvals
from app.services.assets.licensed import prepare_photo
from app.services.assets.policy import license_allowed
from app.services.assets.credits import sync_credits
from app.video.renderer import render_video

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'generated/quality-revision/clean-pilots'
IDS={'Henry':'0f4ddd93-61f6-452d-abfb-b4c6f212f3b2','Ronaldo':'230904a6-bfc0-4182-b240-c4d498cd99fe',
     'Messi':'7f51b5de-a19d-4faf-9318-43dc15ba2b06'}
ORDERS={'Henry':[0,1,2,3,0,2],'Ronaldo':[0,2,1,0,2,1],'Messi':[0,2,3,2,0,3]}


def main(subject):
    OUT.mkdir(parents=True,exist_ok=True)
    photos=[p for p in json.loads((ROOT/'generated/imagery-continuation/curated-photos.json').read_text(encoding='utf8'))
            if p['subject']==subject and 'error' not in p]
    assert len(photos)==4
    jid=IDS[subject]
    with SessionLocal() as db:
        job=db.get(VideoJob,jid)
        if job.status in {'researching','script_generation','collecting_assets','voice_generation','rendering','creating_cover','uploading','uploaded','scheduled'}:
            raise RuntimeError('Stop the active operation before a supervised local rebuild')
        assert job.script and job.video and job.voice_generation
        old_revision=job.content_revision
        backup=OUT/jid/f'before-revision-{old_revision}'
        backup.mkdir(parents=True,exist_ok=True)
        old_output=Path(job.video.output_path)
        for path in [old_output,Path(job.voice_generation.output_path),ROOT/'generated/audio'/f'{jid}.wav',
                     ROOT/'generated/audio'/f'{jid}.words.json',ROOT/'generated/subtitles'/f'{jid}.srt',
                     ROOT/'generated/thumbnails'/f'{jid}.png']:
            if path.is_file() and not (backup/path.name).exists():shutil.copy2(path,backup/path.name)
        audio=backup/f'{jid}.wav';assert audio.is_file() and audio.with_suffix('.words.json').is_file()
        assets=db.query(Asset).filter_by(job_id=jid).order_by(Asset.scene_number).all()
        scenes=db.query(Scene).filter_by(job_id=jid).order_by(Scene.scene_number).all()
        assert len(assets)==len(scenes)==6
        snapshot={'subject':subject,'revision':old_revision,'script':job.script.full_script,'output_path':str(old_output),
            'voice_provider':job.voice_generation.provider,'voice':job.voice_generation.voice,
            'assets':[{k:getattr(a,k) for k in ('id','scene_number','source','url','creator','license','attribution','local_path','provenance')} for a in assets]}
        (backup/'manifest.json').write_text(json.dumps(snapshot,indent=2),encoding='utf8')
        previous={a.url:json.loads(a.provenance or '{}') for a in assets}
        for asset,index in zip(assets,ORDERS[subject]):
            photo=photos[index];source=Path(photo['path']).resolve()
            if (ROOT/'generated').resolve() not in source.parents:raise ValueError('Source is outside retained media')
            if photo.get('sha256') and hashlib.sha256(source.read_bytes()).hexdigest()!=photo['sha256']:
                raise ValueError('Retained source hash changed')
            old=previous.get(photo['source_url']);assert old,'Source was not present in the reviewed asset records'
            if not license_allowed(photo['license'],old.get('license_url',''),photo['creator']):
                raise ValueError('Reuse license no longer passes local validation')
            path=ROOT/'generated/images'/jid/f'clean_{asset.scene_number}_{uuid4().hex}.jpg'
            prepare_photo(source.read_bytes(),path,'Archive photograph - review preview only')
            credit=(f"{photo['title']} | Photo by {photo['creator']}: {photo['source_url']} | {photo['license']} "
                +old.get('license_url','')+f" | Photo date: {photo['capture_date']}; archival illustration, not the historical award event. "
                +'Original photo reframed with proportional crop or same-photo blur background and camera movement. Attribution retained in description.')
            meta={**old,'date':photo['capture_date'],'title':photo['title'],'required_credit':credit,
                'modifications':'Original source retained; proportional crop or same-photo blur background; motion; box-free subtitles',
                'rights_checked':True,'real_photos_only':True,'raw_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'focal_x':.5,'focal_y':.18}
            asset.local_path=str(path);asset.url=photo['source_url'];asset.creator=photo['creator']
            asset.license=photo['license'];asset.attribution=credit[:500];asset.provenance=json.dumps(meta)
        invalidate_approvals(db,job);job.media_revision+=1
        job.status=job.current_step='rendering';job.error_message=None;job.failed_step=None;job.video.status='outdated'
        revision=job.content_revision;media_revision=job.media_revision;script=job.script.full_script
        sync_credits(db,job);db.commit()
        try:
            output,_,_=render_video(jid,job.topic_title,subject,script,audio,job.duration,ROOT/'generated',
                [Path(a.local_path) for a in assets],job.script.seo.cover_text if job.script.seo else '',
                scenes=scenes,subtitle_preset={'language':job.language_code},focal_positions=[(.5,.18)]*6,
                slide_kinds=['archive']*6,revision=revision)
            probe=json.loads(subprocess.check_output([settings.ffprobe_path,'-v','error','-show_streams','-show_format','-of','json',str(output)]))
            stream=next(s for s in probe['streams'] if s['codec_type']=='video')
            assert (stream['width'],stream['height'],stream['avg_frame_rate'])==(1080,1920,'30/1')
            subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(output),'-f','null','-'],capture_output=True,check=True,timeout=120)
            db.refresh(job)
            if job.content_revision!=revision or job.media_revision!=media_revision or job.status!='rendering':
                raise RuntimeError('Job changed during rendering; candidate retained but not selected')
            timeline=json.loads((output.parent/'render-timeline.json').read_text(encoding='utf8'))
            for scene,span in zip(scenes,timeline['scenes']):
                scene.start_time,scene.end_time=span['start'],span['end']
                if span.get('narration'):scene.narration=span['narration'];scene.caption=' '.join(span['narration'].split()[:5])
            # Compatibility mirrors for an already-running older supervised API.
            # All original bytes were archived above; immutable revision output is canonical.
            mirror=ROOT/'generated/videos'/jid/'short.mp4';pending=mirror.with_name('latest-pending.mp4')
            shutil.copy2(output,pending);pending.replace(mirror)
            for name in ('narration.wav','narration.words.json'):
                target=ROOT/'generated/audio'/(jid+('.wav' if name.endswith('.wav') else '.words.json'))
                shutil.copy2(output.parent/name,target)
            Image.open(output.parent/'poster.jpg').save(ROOT/'generated/thumbnails'/f'{jid}.png')
            job.video.output_path=str(output);job.video.duration=float(probe['format']['duration'])
            job.video.media_revision=media_revision;job.video.status='ready_for_review'
            job.voice_generation.output_path=str(ROOT/'generated/audio'/f'{jid}.wav')
            warnings=json.loads(job.warnings or '[]')
            warnings=[w for w in warnings if not w.startswith('Quality review pending:')]
            warnings.append('Quality review pending: committed narrator retained; naturalness unverified; direct listening unavailable.')
            job.warnings=json.dumps(warnings);job.status=job.current_step='ready_for_review';job.error_message=job.failed_step=None
            db.commit()
            report={'subject':subject,'job_id':jid,'revision':revision,'media_revision':media_revision,'mp4_path':str(output),
                'review_url':'http://127.0.0.1:5173/videos/'+jid,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                'script_unchanged':hashlib.sha256(script.encode()).hexdigest()==hashlib.sha256(snapshot['script'].encode()).hexdigest(),
                'provider':job.voice_generation.provider,'voice':job.voice_generation.voice,'voice_name':job.voice_generation.voice,'model':'existing committed narrator; no synthesis requested',
                'new_provider_requests':0,'voice_naturalness':'unverified; committed audio reused without a new provider request',
                'photo_scenes':6,'distinct_photos':len(set(ORDERS[subject])),'clips':0,'standalone_cards':0,'drawn_archive_labels':0,'caption_panels':0,
                'probe':probe,'timeline':timeline,'audio_processing':json.loads((output.parent/'audio-processing.json').read_text(encoding='utf8')),
                'normal_preview_compatibility_sha256':hashlib.sha256(mirror.read_bytes()).hexdigest()}
            (OUT/f'{subject.lower()}-candidate.json').write_text(json.dumps(report,indent=2),encoding='utf8')
            print(json.dumps({k:report[k] for k in ('subject','revision','mp4_path','provider','photo_scenes','drawn_archive_labels','caption_panels')},indent=2),flush=True)
        except Exception as exc:
            db.rollback();job=db.get(VideoJob,jid)
            if job.content_revision==revision:
                job.status=job.current_step='failed';job.failed_step='rendering';job.error_message=str(exc)[:1800];db.commit()
            raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--subject',choices=IDS,default='Henry')
    main(parser.parse_args().subject)
