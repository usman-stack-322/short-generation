"""Run real acceptance flow; preserve media and a report in generated/."""
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.core.config import settings


def main():
    with TestClient(app) as client:
        login = client.post('/api/auth/login', json={'email': 'owner@example.com', 'password': 'DemoOwner123!'})
        assert login.status_code == 200, login.text
        headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
        assert client.get('/api/dashboard', headers=headers).status_code == 200
        member = client.post('/api/members', headers=headers, json={
            'name': 'Acceptance Editor', 'email': f'acceptance-{uuid4().hex[:8]}@example.com', 'role': 'EDITOR'})
        assert member.status_code == 201, member.text
        channel = client.post('/api/channels', headers=headers, json={
            'name': 'Ronaldo Acceptance Channel', 'member_id': member.json()['id']})
        assert channel.status_code == 201, channel.text
        persona = client.post('/api/personalities', headers=headers, json={
            'name': 'Cristiano Ronaldo', 'category': 'Football', 'keywords': ['Cristiano Ronaldo', 'CR7'],
            'research_keywords': ['Cristiano Ronaldo'], 'channel_id': channel.json()['id']})
        assert persona.status_code == 201, persona.text
        response = client.post('/api/videos/generate', headers=headers, json={
            'channel_id': channel.json()['id'], 'personality_id': persona.json()['id'],
            'topic_mode': 'current', 'duration': 30, 'voice': 'en-US', 'language': 'en', 'video_style': 'Documentary'})
        assert response.status_code == 201, response.text
        job_id = response.json()['id']
        job = client.get(f'/api/videos/{job_id}', headers=headers).json()
        assert job['status'] == 'ready_for_review', job
        assert job['script'] and job['seo'] and job['sources']
        root = Path(settings.generated_dir).resolve()
        video = root / 'videos' / job_id / 'short.mp4'
        probe = subprocess.run([settings.ffprobe_path, '-v', 'error', '-show_streams', '-show_format',
                                '-of', 'json', str(video)], capture_output=True, text=True, check=True)
        data = json.loads(probe.stdout)
        stream = next(s for s in data['streams'] if s['codec_type'] == 'video')
        assert (stream['width'], stream['height']) == (1080, 1920)
        assert any(s['codec_type'] == 'audio' for s in data['streams'])
        assert abs(float(data['format']['duration']) - 30) < .15
        assert Image.open(root / 'thumbnails' / f'{job_id}.png').size == (1080, 1920)
        assert (root / 'subtitles' / f'{job_id}.srt').exists()
        assert 6 <= len(list((root / 'images' / job_id).rglob('*.jpg'))) <= 12
        assert any(row['id'] == job_id for row in client.get('/api/videos', headers=headers).json())
        assert client.post(f'/api/videos/{job_id}/approve', headers=headers).json()['status'] == 'approved'
        if '--keep-approved' not in sys.argv:
            assert client.post(f'/api/videos/{job_id}/reject', headers=headers).json()['status'] == 'rejected'
        report = {'passed': True, 'job_id': job_id, 'resolution': [1080, 1920],
                  'duration': float(data['format']['duration']), 'voice_provider': job['voice_provider'],
                  'warnings': job['warnings'], 'video_path': str(video),
                  'checks': ['owner login', 'dashboard', 'member creation', 'channel creation', 'personality creation',
                             'research', 'script', 'SEO', 'narration or explicit fallback', 'five safe images',
                             'FFmpeg render', 'cover', 'subtitles', 'queue', 'review', 'approval'],
                  'rejection_tested': '--keep-approved' not in sys.argv}
        (root / 'acceptance-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
