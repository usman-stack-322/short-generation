import json
from types import SimpleNamespace
from uuid import uuid4

from app.core.security import new_id
from app.database.migrate import migrate_database
from app.database.session import SessionLocal
from app.models import CelebrityAsset, CelebrityFolder, Workspace
from app.services.celebrity_vault import match_celebrity_asset, scan_celebrity_folder
from app.services import title_research, title_shorts


def test_read_youtube_handles_nested_runs_and_json3_without_fake_filler(monkeypatch):
    caption_json = json.dumps({
        'events': [
            {
                'segs': [
                    {'utf8': 'Gilbert Arenas and Iman Shumpert debated locker room leadership for forty seconds on the show. '},
                    {'utf8': 'Shumpert explained how championship habits shaped every practice while Nick Young reacted live in studio.'},
                ]
            }
        ]
    })
    watch_html = (
        '<html><title>Gil Clashes With Shumpert - YouTube</title>'
        '<script>var ytInitialPlayerResponse = {"captions":{"playerCaptionsTracklistRenderer":'
        '{"captionTracks":[{"baseUrl":"https://www.youtube.com/api/timedtext?v=dQw4w9WgXcQ&lang=en",'
        '"name":{"runs":[{"text":"English"}]},"languageCode":"en"}]}},'
        '"videoDetails":{"shortDescription":"Short breakdown"}};</script></html>'
    )

    monkeypatch.setattr(
        title_research,
        'public_get',
        lambda url, **kwargs: (json.dumps({'title': 'Gil Clashes With Shumpert', 'author_name': 'WTW HOOPS', 'author_url': ''}), {}),
    )

    class FakeResp:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

        def json(self):
            return json.loads(self.text)

    def fake_get(url, **kwargs):
        if 'timedtext' in url:
            return FakeResp(200, caption_json)
        return FakeResp(200, watch_html)

    monkeypatch.setattr(title_research.httpx, 'get', fake_get)
    monkeypatch.setattr(title_research.httpx, 'post', lambda url, **kwargs: FakeResp(200, '{}'))

    src, media = title_research.read_youtube('https://www.youtube.com/watch?v=dQw4w9WgXcQ', is_user=True)
    assert src is not None
    assert src['kind'] == 'publisher_transcript'
    assert src['origin'] == 'user_url'
    assert 'Gilbert Arenas and Iman Shumpert debated' in src['excerpt']
    assert 'Video overview and research report' not in src['excerpt']
    assert media['evidence_eligible'] is True

    # When both captions and real description are missing, do NOT fabricate placeholder text
    empty_html = '<html><title>Empty Clip - YouTube</title><script>{"shortDescription":""}</script></html>'
    monkeypatch.setattr(title_research.httpx, 'get', lambda url, **kwargs: FakeResp(200, empty_html))
    monkeypatch.setattr(title_research.httpx, 'post', lambda url, **kwargs: FakeResp(200, '{}'))

    src2, media2 = title_research.read_youtube('https://www.youtube.com/watch?v=dQw4w9WgXcQ', is_user=True)
    assert src2 is None
    assert media2 is not None
    assert media2['evidence_eligible'] is False
    assert 'Video overview' not in media2['excerpt']


def test_collect_uses_rich_user_url_story_without_discovery_noise(monkeypatch):
    long_excerpt = ' '.join(['Gilbert Arenas and Iman Shumpert broke down the playoff mindset and team chemistry.'] * 8)
    fake_source = {
        'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        'title': 'Gil and Shumpert Full Story',
        'excerpt': long_excerpt,
        'retrieved_sha256': 'abc123',
        'kind': 'publisher_transcript',
        'evidence_eligible': True,
        'transcript_status': 'captions extracted',
        'published_at': None,
        'primary_links': [],
        'publisher_group': 'youtube_wtw_hoops',
        'origin': 'user_url',
    }
    monkeypatch.setattr(
        title_research,
        'read_youtube',
        lambda url, is_user=False: (dict(fake_source), {'url': url, 'title': fake_source['title'], 'evidence_eligible': True}),
    )
    monkeypatch.setattr(
        title_research,
        'discover',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('discover should not run when supplied URL has rich script')),
    )

    diag = []
    sources, media = title_research.collect(
        {'topic': 'Gil and Shumpert debate'},
        ['https://www.youtube.com/watch?v=dQw4w9WgXcQ'],
        diag,
        lambda u: True,
        {'people': ['Gilbert Arenas', 'Iman Shumpert']},
        style='educational',
    )
    assert len(sources) == 1
    assert sources[0]['origin'] == 'user_url'
    assert 'Gilbert Arenas and Iman Shumpert' in sources[0]['excerpt']


def test_vault_matcher_headings_aliases_accents_diversity_and_timer_words(tmp_path):
    migrate_database()
    vault = tmp_path / 'vault'
    for folder in ['Iman Shumpert', 'Gilbert Arenas', 'Nick Young', 'Luka Dončić', 'Austin Reaves', 'LeBron James', 'Basketball Highlights']:
        (vault / folder).mkdir(parents=True)
        (vault / folder / 'clip_01.mp4').write_bytes(f'{folder}-video-{uuid4().hex}'.encode())

    ws_id = new_id()
    draft_dir = tmp_path / 'draft_assets'
    with SessionLocal() as db:
        db.add(Workspace(id=ws_id, name='Matcher Test WS'))
        db.commit()
        scan_celebrity_folder(db, ws_id, str(vault), 'mix_both')

        # 1. Headline noun like "Shumpert Clash" must NOT be mistaken for an absent human; matches Iman Shumpert!
        s1 = match_celebrity_asset(
            db, ws_id,
            {
                'number': 1,
                'narration': 'Shumpert opened the floor during a heated exchange on the show.',
                'on_screen_text': 'Shumpert Clash',
                'visual_description': 'Host and guest reacting in a heated sports debate.',
                'image_query': 'NBA sports studio debate reaction',
            },
            draft_dir,
            draft_title='Arenas and Shumpert Clash',
            people=['Gilbert Arenas', 'Iman Shumpert'],
        )
        assert s1 is not None and s1['celebrity_name'] == 'Iman Shumpert'

        # 2. Nickname alias ("Swaggy P" -> "Nick Young")
        s2 = match_celebrity_asset(
            db, ws_id,
            {
                'number': 2,
                'narration': 'Swaggy P chimed in with a blunt take about locker room chemistry.',
                'on_screen_text': 'Swaggy P Reacts',
                'visual_description': 'Swaggy P smiling at the podcast table.',
                'image_query': 'Swaggy P interview reaction',
            },
            draft_dir,
            draft_title='Show Clip',
            people=['Nick Young'],
            existing=[s1],
        )
        assert s2 is not None and s2['celebrity_name'] == 'Nick Young'

        # 3. Unaccented query -> accented vault folder ("Luka Dončić")
        s3 = match_celebrity_asset(
            db, ws_id,
            {
                'number': 3,
                'narration': 'Luka Doncic controlled the fourth quarter pace effortlessly.',
                'visual_description': 'Luka Doncic bringing the ball up court.',
                'image_query': 'Luka Doncic game clip',
            },
            draft_dir,
            draft_title='NBA Finish',
            people=['Luka Doncic'],
            existing=[s1, s2],
        )
        assert s3 is not None and s3['celebrity_name'] == 'Luka Dončić'

        # 4. Minor spelling variant ("Austin Reeves" -> "Austin Reaves")
        s4 = match_celebrity_asset(
            db, ws_id,
            {
                'number': 4,
                'narration': 'Austin Reeves hit back-to-back shots down the stretch.',
                'visual_description': 'Austin Reeves celebrating on court.',
                'image_query': 'Austin Reeves basketball photo',
            },
            draft_dir,
            draft_title='Lakers Finish',
            people=['Austin Reeves'],
            existing=[s1, s2, s3],
        )
        assert s4 is not None and s4['celebrity_name'] == 'Austin Reaves'

        # 5. Explicitly missing external person MUST still return None for web fallback
        s_missing = match_celebrity_asset(
            db, ws_id,
            {
                'number': 5,
                'narration': 'Kevin Garnett offered a fierce championship warning.',
                'visual_description': 'Kevin Garnett speaking intently on camera.',
                'image_query': 'Kevin Garnett editorial photo',
            },
            draft_dir,
            draft_title='Garnett Take',
            people=['Kevin Garnett', 'Iman Shumpert'],
            existing=[s1],
        )
        assert s_missing is None

        db.query(CelebrityAsset).filter_by(workspace_id=ws_id).delete()
        db.query(CelebrityFolder).filter_by(workspace_id=ws_id).delete()
        db.commit()

    # Check calibrated target word range for a 45s normal-pace draft (~90-102 spoken words)
    dummy = SimpleNamespace(duration=45, data=json.dumps({'voice_pace': 'normal', 'narrator': 'automatic'}))
    min_h, max_h, ideal_lo, ideal_hi, target, scene_count = title_shorts._target_word_range(dummy)
    assert scene_count == 4
    assert 85 <= ideal_lo <= target <= ideal_hi <= 108
    assert min_h < ideal_lo and max_h > ideal_hi


def test_openverse_rejects_unrelated_photos_and_only_uses_target_celebrities(monkeypatch, tmp_path):
    bad_item = {
        'source': 'openverse',
        'url': 'https://openverse.org/mic',
        'download_url': 'https://openverse.org/mic.jpg',
        'creator': 'StockUser',
        'license': 'CC BY 2.0',
        'license_url': 'https://creativecommons.org/licenses/by/2.0/',
        'title': 'Podcast microphone on wooden desk',
        'tags': 'microphone audio studio',
        'description': 'Photograph of Podcast microphone on wooden desk',
    }
    watermarked_item = {
        'source': 'openverse',
        'url': 'https://www.gettyimages.com/detail/kevin-garnett',
        'download_url': 'https://media.gettyimages.com/photos/kevin-garnett.jpg',
        'creator': 'Getty Staff',
        'license': 'CC BY 2.0',
        'license_url': 'https://creativecommons.org/licenses/by/2.0/',
        'title': 'Kevin Garnett watermarked stock photo',
        'tags': 'kevin garnett getty alamy',
        'description': 'Photograph of Kevin Garnett',
    }
    good_item = {
        'source': 'openverse',
        'url': 'https://openverse.org/kg',
        'download_url': 'https://openverse.org/kg.jpg',
        'creator': 'SportsPhotog',
        'license': 'CC BY 2.0',
        'license_url': 'https://creativecommons.org/licenses/by/2.0/',
        'title': 'Kevin Garnett postgame press conference',
        'tags': 'kevin garnett nba celtics',
        'description': 'Photograph of Kevin Garnett postgame press conference',
    }
    fake_file = tmp_path / 'dl.jpg'
    fake_file.write_bytes(b'real-kevin-garnett-photo')
    downloaded = []

    monkeypatch.setattr(title_shorts.OpenverseAssetProvider, 'search', lambda self, q: [bad_item, watermarked_item, good_item])
    monkeypatch.setattr(
        title_shorts,
        'download_photo',
        lambda item, sc, folder, mode: (
            downloaded.append(item['url'])
            or SimpleNamespace(
                local_path=fake_file,
                provenance={'original_path': str(fake_file), 'required_credit': item['creator']},
            )
        ),
    )

    scene = {'number': 2, 'image_query': 'NBA debate studio', 'visual_description': 'Kevin Garnett speaking'}
    res = title_shorts.fetch_openverse_visual(scene, tmp_path, used=set(), target_celebrities=['Kevin Garnett'])
    assert res is not None
    assert res['celebrity_name'] == 'Kevin Garnett'
    assert res['source_url'] == 'https://openverse.org/kg'
    assert downloaded == ['https://openverse.org/kg']

    # If Openverse ONLY returns unrelated generic stock items, reject all and return None
    monkeypatch.setattr(title_shorts.OpenverseAssetProvider, 'search', lambda self, q: [bad_item])
    assert title_shorts.fetch_openverse_visual(scene, tmp_path, used=set(), target_celebrities=['Kevin Garnett']) is None


def test_register_creates_isolated_private_workspaces():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import TitleShortDraft

    with TestClient(app) as client:
        r1 = client.post(
            '/api/auth/register',
            json={'name': 'Creator One', 'email': f'{uuid4().hex}@example.com', 'password': 'Password123!'},
        )
        r2 = client.post(
            '/api/auth/register',
            json={'name': 'Creator Two', 'email': f'{uuid4().hex}@example.com', 'password': 'Password123!'},
        )
        assert r1.status_code == 201 and r2.status_code == 201
        d1, d2 = r1.json(), r2.json()
        assert d1['role'] == 'OWNER' and d2['role'] == 'OWNER'
        assert d1['workspace_id'] != d2['workspace_id']

        h1 = {'Authorization': f"Bearer {d1['access_token']}"}
        h2 = {'Authorization': f"Bearer {d2['access_token']}"}
        ws1_list = client.get('/api/workspaces', headers=h1).json()
        ws2_list = client.get('/api/workspaces', headers=h2).json()
        assert [w['workspace_id'] for w in ws1_list] == [d1['workspace_id']]
        assert [w['workspace_id'] for w in ws2_list] == [d2['workspace_id']]

        draft_id = new_id()
        with SessionLocal() as db:
            db.add(TitleShortDraft(
                id=draft_id,
                workspace_id=d1['workspace_id'],
                creator_id=d1['user']['id'],
                title='Private Draft Test',
                duration=45,
                language='English',
                style='storytelling',
                status='script_review',
                data='{}',
            ))
            db.commit()

        assert any(item['id'] == draft_id for item in client.get('/api/title-shorts', headers=h1).json())
        assert all(item['id'] != draft_id for item in client.get('/api/title-shorts', headers=h2).json())
        assert client.get(f'/api/title-shorts/{draft_id}', headers=h2).status_code == 404


