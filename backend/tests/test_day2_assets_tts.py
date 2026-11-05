import base64
import json
import pytest
from app.core.config import settings
from app.core.network import validate_url
from app.services.assets.licensed import CommonsAssetProvider
from app.tts.providers import GoogleTTSProvider,ElevenLabsProvider


def test_commons_rejects_unlicensed_and_unattributed_images(monkeypatch):
    def info(license,artist='Example Photographer'):
        return {'mime':'image/jpeg','url':'https://upload.wikimedia.org/test.jpg','descriptionurl':'https://commons.wikimedia.org/wiki/File:Test',
                'extmetadata':{'LicenseShortName':{'value':license},'LicenseUrl':{'value':'https://creativecommons.org/licenses/by/4.0/'},'Artist':{'value':artist}}}
    payload={'query':{'pages':{'1':{'imageinfo':[info('CC BY 4.0')]},'2':{'imageinfo':[info('All rights reserved')]},
                             '3':{'imageinfo':[info('CC BY 4.0','')]}}}}
    monkeypatch.setattr('app.services.assets.licensed.fetch',lambda *args,**kwargs:(json.dumps(payload).encode(),{}))
    rows=CommonsAssetProvider().search('football')
    assert len(rows)==1 and rows[0]['creator']=='Example Photographer'
    assert rows[0]['license']=='CC BY 4.0'


def test_network_rejects_private_hosts_and_unapproved_redirect_targets(monkeypatch):
    monkeypatch.setattr('app.core.network.socket.getaddrinfo',lambda *args,**kwargs:[(None,None,None,None,('127.0.0.1',443))])
    with pytest.raises(ValueError,match='Private'):validate_url('https://example.com/file')
    with pytest.raises(ValueError):validate_url('http://example.com/file')
    with pytest.raises(ValueError):validate_url('https://example.com/file',{'upload.wikimedia.org'})


def test_google_tts_uses_server_only_key_and_writes_audio(tmp_path,monkeypatch):
    calls={}
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'audioContent':base64.b64encode(b'RIFF-test-audio').decode()}
    def post(url,**kwargs):calls.update({'url':url,**kwargs});return Response()
    monkeypatch.setattr(settings,'google_tts_api_key','fake-tts-secret')
    monkeypatch.setattr('app.tts.providers.httpx.post',post)
    path=tmp_path/'speech.wav'
    assert GoogleTTSProvider().generate_voice('A generic narrator.','en-US',path)=='Google TTS narrator'
    assert path.read_bytes()==b'RIFF-test-audio'
    assert calls['headers']['x-goog-api-key']=='fake-tts-secret'
    assert 'fake-tts-secret' not in calls['url']


def test_elevenlabs_requires_configured_narrator_allowlist(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'elevenlabs_api_key','fake-key')
    monkeypatch.setattr(settings,'elevenlabs_voice_id','unapproved-voice')
    monkeypatch.setattr(settings,'elevenlabs_allowed_voice_ids','approved-narrator')
    with pytest.raises(RuntimeError,match='generic narrator'):
        ElevenLabsProvider().generate_voice('Test','unapproved-voice',tmp_path/'voice.wav')


def test_workspace_settings_music_and_viewer_validation(publishable):
    p=publishable;c=p['client']
    settings_result=c.get('/api/settings',headers=p['editor']).json()
    assert isinstance(settings_result['providers']['gemini'],bool)
    assert 'google_client_secret' not in json.dumps(settings_result)
    assert c.put('/api/settings',headers=p['editor'],json=settings_result['preferences']).status_code==403
    invalid={**settings_result['preferences'],'subtitle_mode':'unsafe'}
    assert c.put('/api/settings',headers=p['owner'],json=invalid).status_code==422
    response=c.post('/api/music',headers=p['owner'],data={'source':'test','license':'Original','attribution':'test'},
                    files={'file':('../../malware.exe',b'not audio','application/octet-stream')})
    assert response.status_code==422
