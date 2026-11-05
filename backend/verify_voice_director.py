"""Offline acceptance profiles plus a real local TTS/FFmpeg pipeline regression."""
import json
import subprocess
from pathlib import Path
from app.core.config import settings
from app.core.security import new_id
from app.database.session import SessionLocal
from app.models import Channel, Personality, Topic, VideoJob, Script
from app.services.pipeline import run_pipeline
from app.tts.director import direct_voice


def main():
    assert not settings.youtube_uploads_enabled
    samples = [
        ('Cristiano Ronaldo tactical/career analysis', 'professional'),
        ('Funny celebrity moment', 'funny'),
        ('Ronaldo major record achievement', 'sports_hype'),
        ('Emotional retirement/career retrospective', 'emotional'),
    ]
    profiles = []
    for topic, expected in samples:
        profile = direct_voice(topic, {'hook':topic}, 'Cristiano Ronaldo', 'Sports')
        assert profile.style == expected
        profiles.append({'topic':topic, 'profile':profile.model_dump()})
    root = Path(settings.generated_dir).resolve()
    cached = json.loads((root/'gemini-fallback-verification.json').read_text(encoding='utf-8'))['generated_script']
    # No cloud calls: reuse the previously generated script and local/demo visuals.
    settings.gemini_api_key = ''
    settings.asset_provider = 'demo'
    with SessionLocal() as db:
        personality = db.query(Personality).filter(Personality.name == 'Cristiano Ronaldo').first()
        channel = db.get(Channel, personality.channel_id) if personality and personality.channel_id else db.query(Channel).first()
        assert personality and channel
        topic = Topic(id=new_id(), personality_id=personality.id, channel_id=channel.id,
                      title='Ronaldo major record achievement — voice director acceptance', verification_status='demo',
                      source_name='Local acceptance test; cached historical script')
        db.add(topic); db.flush()
        job = VideoJob(id=new_id(), workspace_id=channel.workspace_id, channel_id=channel.id,
                       personality_id=personality.id, topic_id=topic.id, topic_title=topic.title,
                       duration=30, voice='en-US', tts_provider='local', voice_style='auto')
        db.add(job); db.flush()
        job.script = Script(id=new_id(), job_id=job.id, **{k:cached[k] for k in
                            ('hook','context','main_story','why_it_matters','ending','full_script')})
        db.add(job.script); db.commit()
        result = run_pipeline(db,job,personality,channel,'voice')
        assert result['status'] == 'ready_for_review'
        assert result['voice_direction']['style'] == 'sports_hype'
        path = root/'videos'/job.id/'short.mp4'
        check = subprocess.run([settings.ffprobe_path,'-v','error','-show_streams','-show_format','-of','json',str(path)],
                               check=True,capture_output=True,text=True,timeout=20)
        media = json.loads(check.stdout)
        video = next(s for s in media['streams'] if s['codec_type']=='video')
        assert (video['width'], video['height'], video['codec_name']) == (1080,1920,'h264')
        assert any(s['codec_name']=='aac' for s in media['streams'])
        report = {'samples':profiles, 'job_id':job.id,'status':result['status'],'provider':result['voice_provider'],
                  'voice_direction':result['voice_direction'],'video_path':str(path),
                  'width':video['width'],'height':video['height'],'duration':media['format']['duration'],
                  'uploads_enabled':settings.youtube_uploads_enabled}
        (root/'voice-director-acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2))


if __name__ == '__main__':
    main()
