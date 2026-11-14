import inspect
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import TypeAdapter, ValidationError
from starlette.routing import Match

from app.core.config import settings
from app.core.security import new_id
from app.database.migrate import migrate_database
from app.database.seed import bootstrap_initial_owner, seed_demo_data
from app.database.session import SessionLocal, get_db
from app.models import TitleShortDraft


class _SyncResponse:
    def __init__(self, status_code: int, body, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = {}
        items = headers or []
        if isinstance(items, dict):
            items = items.items()
        for k, v in items:
            kl = (k.decode('latin-1') if isinstance(k, bytes) else str(k)).lower()
            vl = v.decode('latin-1') if isinstance(v, bytes) else str(v)
            self.headers[kl] = f'{self.headers[kl]}, {vl}' if kl in self.headers else vl

    def json(self):
        return self._body

    @property
    def text(self) -> str:
        return json.dumps(self._body) if not isinstance(self._body, str) else self._body


class SyncRouterClient:
    """Deterministic in-process FastAPI route dispatcher (no socketpair/threadpool deadlocks)."""

    def __init__(self, app):
        self.app = app

    def _iter_routes(self):
        for r in self.app.routes:
            if isinstance(r, APIRoute):
                yield r
            elif hasattr(r, 'effective_candidates'):
                ec = r.effective_candidates
                for cand in (ec() if callable(ec) else ec):
                    yield cand

    def _find_route(self, method: str, path: str):
        for r in self._iter_routes():
            if method in getattr(r, 'methods', ()):
                m = r.path_regex.match(path)
                if m:
                    return r, m.groupdict()
        raise AssertionError(f'No FastAPI route matches {method} {path}')

    def _solve_dep(self, dep, request: Request, response: Response, path_params: dict, query_params: dict, body_data, db):
        if dep.call is get_db:
            return db
        if isinstance(dep.call, HTTPBearer):
            auth = request.headers.get('authorization', '')
            if auth.lower().startswith('bearer '):
                return HTTPAuthorizationCredentials(scheme='Bearer', credentials=auth.split(' ', 1)[1].strip())
            if getattr(dep.call, 'auto_error', True):
                raise HTTPException(401, 'Not authenticated')
            return None

        kwargs = {}
        if dep.request_param_name:
            kwargs[dep.request_param_name] = request
        if dep.response_param_name:
            kwargs[dep.response_param_name] = response
        if dep.http_connection_param_name:
            kwargs[dep.http_connection_param_name] = request

        for p in dep.path_params:
            kwargs[p.name] = path_params[p.name]

        for p in dep.query_params:
            if p.alias in query_params:
                raw_val = query_params[p.alias][0]
                kwargs[p.name] = TypeAdapter(p.field_info.annotation).validate_python(raw_val)

        for p in dep.body_params:
            if body_data is None:
                raise HTTPException(422, f'Missing body parameter {p.name}')
            kwargs[p.name] = TypeAdapter(p.field_info.annotation).validate_python(body_data)

        sig = inspect.signature(dep.call)
        for pname, param in sig.parameters.items():
            if param.annotation is BackgroundTasks:
                kwargs[pname] = BackgroundTasks()

        for sub in dep.dependencies:
            sub_val = self._solve_dep(sub, request, response, path_params, query_params, body_data, db)
            if sub.name:
                kwargs[sub.name] = sub_val

        return dep.call(**kwargs)

    def request(self, method: str, url: str, headers: dict | None = None, json: dict | None = None):
        parsed = urlsplit(url)
        route, path_params = self._find_route(method.upper(), parsed.path)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        raw_headers = [(k.lower().encode('latin-1'), str(v).encode('latin-1')) for k, v in (headers or {}).items()]
        scope = {
            'type': 'http',
            'method': method.upper(),
            'path': parsed.path,
            'raw_path': parsed.path.encode('utf-8'),
            'query_string': parsed.query.encode('utf-8'),
            'headers': raw_headers,
            'scheme': 'http',
            'server': ('testserver', 80),
        }
        req = Request(scope)
        res = Response()
        db = SessionLocal()
        try:
            result = self._solve_dep(route.dependant, req, res, path_params, query_params, json, db)
            hdrs = list(res.raw_headers)
            if isinstance(result, FileResponse):
                return _SyncResponse(200, {'file': str(result.path)}, hdrs)
            status = getattr(route, 'status_code', None) or getattr(getattr(route, 'original_route', None), 'status_code', None) or 200
            return _SyncResponse(status, result, hdrs)
        except ValidationError as exc:
            return _SyncResponse(422, {'detail': exc.errors()})
        except HTTPException as exc:
            return _SyncResponse(exc.status_code, {'detail': exc.detail})
        finally:
            db.close()

    def get(self, url: str, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request('POST', url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request('PUT', url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self.request('PATCH', url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request('DELETE', url, **kwargs)


@pytest.fixture(scope='module')
def client():
    from app.main import app

    migrate_database()
    seed_demo_data()
    yield SyncRouterClient(app)


def _login(client, email: str, password: str) -> dict[str, str]:
    res = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert res.status_code == 200, res.text
    return {'Authorization': 'Bearer ' + res.json()['access_token']}


def _create_draft_row(workspace_id: str, creator_id: str, title: str, rendered: bool = True) -> tuple[str, Path]:
    draft_id = new_id()
    video_dir = Path(settings.generated_dir).resolve() / 'title-shorts' / draft_id / 'render-1'
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / 'short.mp4'
    video_path.write_bytes(b'fake-mp4-binary-stream')

    scenes = [
        {
            'number': i + 1,
            'start': i * 10,
            'end': (i + 1) * 10,
            'narration': f'Scene {i + 1} verified narration for {title}.',
            'visual_description': 'Host speaking cleanly',
            'image_query': 'Host speaking',
            'on_screen_text': f'Fact {i + 1}',
            'motion': 'push_in',
            'transition': 'dissolve',
            'ai_image_prompt': 'Studio interview frame',
        }
        for i in range(3)
    ]
    data = {
        'research_state': 'verified',
        'analysis': {'topic': title, 'people': ['Stephen A. Smith']},
        'sources': [{'id': 'S1', 'url': 'https://example.edu/s1', 'excerpt': 'Verified source'}],
        'plan': {'scenes': scenes, 'claims': []},
        'assets': [None, None, None],
        'review_status': 'pending_review' if rendered else 'draft',
    }
    if rendered:
        rec = {'path': str(video_path), 'duration': 30.0, 'revision': 1, 'sha256': 'abc'}
        data['video'] = rec
        data['renders'] = [rec]

    with SessionLocal() as db:
        db.add(
            TitleShortDraft(
                id=draft_id,
                workspace_id=workspace_id,
                creator_id=creator_id,
                title=title,
                duration=30,
                language='English',
                style='educational',
                status='ready' if rendered else 'script_review',
                revision=1,
                data=json.dumps(data),
            )
        )
        db.commit()
    return draft_id, video_path


def test_owner_and_friend_isolated_workspaces(client):
    suffix = uuid4().hex[:8]
    owner_email = f'owner-{suffix}@example.com'
    friend_email = f'friend-{suffix}@example.com'
    bootstrap_initial_owner(owner_email, 'OwnerPass123!', 'Main Owner')

    owner_h = _login(client, owner_email, 'OwnerPass123!')
    owner_me = client.get('/api/auth/me', headers=owner_h).json()
    owner_ws = owner_me['workspace_id']

    # Owner creates a private channel & short in their workspace
    owner_ch = client.post('/api/channels', headers=owner_h, json={'name': 'Owner Main Channel'})
    assert owner_ch.status_code == 201, owner_ch.text
    owner_draft_id, _ = _create_draft_row(owner_ws, owner_me['id'], 'Owner Private Draft')

    # Owner invites Friend as isolated ADMIN workspace owner
    invite = client.post(
        '/api/team/invite',
        headers=owner_h,
        json={'name': 'Friend Owner', 'email': friend_email, 'role': 'ADMIN'},
    )
    assert invite.status_code == 201, invite.text
    inv_data = invite.json()
    assert inv_data['isolated'] is True
    assert inv_data['workspace_id'] != owner_ws
    friend_pw = inv_data['temporary_password']
    assert friend_pw

    friend_h = _login(client, friend_email, friend_pw)
    friend_me = client.get('/api/auth/me', headers=friend_h).json()
    friend_ws = friend_me['workspace_id']
    assert friend_ws != owner_ws

    # Friend creates their own channel & draft in Friend workspace
    friend_ch = client.post('/api/channels', headers=friend_h, json={'name': 'Friend Isolated Channel'})
    assert friend_ch.status_code == 201, friend_ch.text
    friend_draft_id, _ = _create_draft_row(friend_ws, friend_me['id'], 'Friend Private Draft')

    # Mutual 100% isolation assertions
    owner_spaces = [w['workspace_id'] for w in client.get('/api/workspaces', headers=owner_h).json()]
    friend_spaces = [w['workspace_id'] for w in client.get('/api/workspaces', headers=friend_h).json()]
    assert owner_ws in owner_spaces and friend_ws not in owner_spaces
    assert friend_ws in friend_spaces and owner_ws not in friend_spaces

    owner_members = [m['email'] for m in client.get('/api/members', headers=owner_h).json()]
    friend_members = [m['email'] for m in client.get('/api/members', headers=friend_h).json()]
    assert friend_email not in owner_members
    assert owner_email not in friend_members

    # Neither sees the other's channels or title shorts (even with spoofed X-Workspace-Id!)
    spoof_friend = {**friend_h, 'X-Workspace-Id': owner_ws}
    assert [c['name'] for c in client.get('/api/channels', headers=spoof_friend).json()] == ['Friend Isolated Channel']
    assert client.get(f'/api/channels/{owner_ch.json()["id"]}', headers=spoof_friend).status_code == 404
    assert [d['id'] for d in client.get('/api/title-shorts', headers=spoof_friend).json()] == [friend_draft_id]
    assert client.get(f'/api/title-shorts/{owner_draft_id}', headers=spoof_friend).status_code == 404
    assert client.get(f'/api/title-shorts/{friend_draft_id}', headers=owner_h).status_code == 404
    assert client.put(
        f'/api/team/members/{inv_data["id"]}/role',
        headers=owner_h,
        json={'role': 'MEMBER'},
    ).status_code == 404


def test_employee_rbac_and_approval_gated_download(client, tmp_path, monkeypatch):
    suffix = uuid4().hex[:8]
    owner_email = f'boss-{suffix}@example.com'
    emp1_email = f'emp1-{suffix}@example.com'
    emp2_email = f'emp2-{suffix}@example.com'
    bootstrap_initial_owner(owner_email, 'BossPass123!', 'Studio Owner')

    owner_h = _login(client, owner_email, 'BossPass123!')
    owner_me = client.get('/api/auth/me', headers=owner_h).json()
    ws_id = owner_me['workspace_id']

    # Owner creates a channel and connects a shared Celebrity Folder
    owner_ch = client.post('/api/channels', headers=owner_h, json={'name': 'Studio Channel'}).json()['id']
    vault = tmp_path / f'vault-{suffix}'
    (vault / 'Stephen A. Smith').mkdir(parents=True)
    (vault / 'Stephen A. Smith' / 'react.jpg').write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')
    scan = client.post('/api/assets/connect-folder', headers=owner_h, json={'folder_path': str(vault), 'preference': 'mix_both'})
    assert scan.status_code == 200, scan.text

    # Owner invites 2 employees into the workspace
    e1_inv = client.post('/api/team/invite', headers=owner_h, json={'name': 'Employee One', 'email': emp1_email, 'role': 'MEMBER'}).json()
    e2_inv = client.post('/api/team/invite', headers=owner_h, json={'name': 'Employee Two', 'email': emp2_email, 'role': 'MEMBER'}).json()
    emp1_h = _login(client, emp1_email, e1_inv['temporary_password'])
    emp2_h = _login(client, emp2_email, e2_inv['temporary_password'])
    emp1_me = client.get('/api/auth/me', headers=emp1_h).json()
    emp2_me = client.get('/api/auth/me', headers=emp2_h).json()

    # Employees CAN browse Celebrity Library (read/use-only) and stream files
    lib = client.get('/api/assets/library', headers=emp1_h)
    assert lib.status_code == 200
    assert lib.json()['total_assets'] >= 1
    first_asset_url = lib.json()['celebrities'][0]['assets'][0]['preview_url']
    assert client.get(first_asset_url, headers=emp1_h).status_code == 200

    # Employees CANNOT add/upload Vault assets or access/create channels/team/youtube
    assert client.post('/api/assets/connect-folder', headers=emp1_h, json={'folder_path': str(vault), 'preference': 'mix_both'}).status_code == 403
    assert client.get('/api/channels', headers=emp1_h).status_code == 403
    assert client.post('/api/channels', headers=emp1_h, json={'name': 'Rogue'}).status_code == 403
    assert client.patch(f'/api/channels/{owner_ch}', headers=emp1_h, json={'niche': 'x'}).status_code == 403
    assert client.get('/api/youtube/connect', headers=emp1_h).status_code == 403
    assert client.post('/api/youtube/disconnect', headers=emp1_h, json={'channel_id': owner_ch}).status_code == 403
    assert client.get('/api/members', headers=emp1_h).status_code == 403
    assert client.post('/api/team/invite', headers=emp1_h, json={'name': 'Rogue User', 'email': f'x-{suffix}@example.com', 'role': 'MEMBER'}).status_code == 403

    # Employees CANNOT attach a channel on Create Short, even via API
    monkeypatch.setattr('app.ai.smart_router.has_any_ai_configured', lambda: True)
    blocked_create = client.post(
        '/api/title-shorts',
        headers=emp1_h,
        json={'title': 'Stephen A Smith Reaction Story Today', 'duration': 30, 'channel_id': owner_ch},
    )
    assert blocked_create.status_code == 403

    # Each employee sees ONLY their own drafts; Owner sees all workspace drafts
    emp1_draft, _ = _create_draft_row(ws_id, emp1_me['id'], 'Emp 1 Story', rendered=True)
    emp2_draft, _ = _create_draft_row(ws_id, emp2_me['id'], 'Emp 2 Story', rendered=True)

    assert [d['id'] for d in client.get('/api/title-shorts', headers=emp1_h).json()] == [emp1_draft]
    assert [d['id'] for d in client.get('/api/title-shorts', headers=emp2_h).json()] == [emp2_draft]
    assert client.get(f'/api/title-shorts/{emp2_draft}', headers=emp1_h).status_code == 404
    owner_ids = {d['id'] for d in client.get('/api/title-shorts', headers=owner_h).json()}
    assert {emp1_draft, emp2_draft}.issubset(owner_ids)

    # Employee dashboard hides channels & team_activity and filters recent_shorts to creator only
    emp_dash = client.get('/api/dashboard', headers=emp1_h).json()
    assert emp_dash['channels'] == []
    assert emp_dash['total_channels'] == 0
    assert 'team_activity' not in emp_dash
    assert [s['id'] for s in emp_dash['recent_shorts']] == [emp1_draft]

    # Employee CAN delete their own unsubmitted/rejected draft before submitting
    emp1_temp_draft, _ = _create_draft_row(ws_id, emp1_me['id'], 'Emp 1 Disposable Draft', rendered=False)
    emp1_temp_proj, _ = _create_draft_row(ws_id, emp1_me['id'], 'Emp 1 Disposable Project', rendered=False)
    assert client.delete(f'/api/title-shorts/{emp1_temp_draft}', headers=emp1_h).status_code == 200
    assert client.get(f'/api/title-shorts/{emp1_temp_draft}', headers=emp1_h).status_code == 404
    assert client.delete(f'/api/projects/{emp1_temp_proj}', headers=emp1_h).status_code == 200
    assert client.get(f'/api/title-shorts/{emp1_temp_proj}', headers=emp1_h).status_code == 404

    # Employee CANNOT delete another employee's draft
    assert client.delete(f'/api/title-shorts/{emp2_draft}', headers=emp1_h).status_code == 404

    # Employee submits draft; download stays LOCKED (403) until Owner approves
    sub = client.post(f'/api/projects/{emp1_draft}/submit-review', headers=emp1_h)
    assert sub.status_code == 200
    assert client.get(f'/api/title-shorts/{emp1_draft}/media/video?revision=1&download=false', headers=emp1_h).status_code == 200
    assert client.get(f'/api/title-shorts/{emp1_draft}/media/video?revision=1&download=true', headers=emp1_h).status_code == 403

    # Owner can always download immediately
    assert client.get(f'/api/title-shorts/{emp1_draft}/media/video?revision=1&download=true', headers=owner_h).status_code == 200

    # Employee CANNOT self-approve, delete, or upload to YouTube
    assert client.post(f'/api/projects/{emp1_draft}/review', headers=emp1_h, json={'action': 'approve', 'note': 'self'}).status_code == 403
    assert client.post(f'/api/projects/{emp1_draft}/upload-youtube', headers=emp1_h, json={'title': 'X', 'description': 'Y'}).status_code == 403
    assert client.delete(f'/api/projects/{emp1_draft}', headers=emp1_h).status_code == 403
    assert client.delete(f'/api/title-shorts/{emp1_draft}', headers=emp1_h).status_code == 403

    # Owner approves -> Employee 1 download unlocks (200)
    appr = client.post(f'/api/projects/{emp1_draft}/review', headers=owner_h, json={'action': 'approve', 'note': 'Looks great'})
    assert appr.status_code == 200
    assert appr.json()['review_status'] == 'approved'
    assert client.get(f'/api/title-shorts/{emp1_draft}/media/video?revision=1&download=true', headers=emp1_h).status_code == 200

    # Owner can delete a draft
    assert client.delete(f'/api/title-shorts/{emp2_draft}', headers=owner_h).status_code == 200
    assert client.get(f'/api/title-shorts/{emp2_draft}', headers=owner_h).status_code == 404


def test_shareable_invite_links_and_role_updates(client):
    suffix = uuid4().hex[:8]
    owner_email = f'linkowner-{suffix}@example.com'
    bootstrap_initial_owner(owner_email, 'OwnerLink123!', 'Link Owner')
    owner_h = _login(client, owner_email, 'OwnerLink123!')
    owner_ws = client.get('/api/auth/me', headers=owner_h).json()['workspace_id']

    # 1. Owner generates an open Shareable Link for an Employee
    emp_link = client.post(
        '/api/team/invite-links',
        headers=owner_h,
        json={'role': 'MEMBER', 'isolated': False, 'label': 'Editor Link'},
    )
    assert emp_link.status_code == 201, emp_link.text
    emp_token = emp_link.json()['token']
    assert '/join?invite=' in emp_link.json()['invite_path']

    preview = client.get(f'/api/invites/{emp_token}')
    assert preview.status_code == 200
    assert preview.json()['role'] == 'MEMBER'
    assert preview.json()['isolated'] is False

    # Invited employee opens link and sets their own name, email & password
    emp_joined = client.post(
        '/api/invites/accept',
        json={
            'token': emp_token,
            'name': 'Link Joined Employee',
            'email': f'joined-emp-{suffix}@example.com',
            'password': 'MyCustomPass123!',
        },
    )
    assert emp_joined.status_code == 201, emp_joined.text
    assert emp_joined.json()['role'] == 'MEMBER'
    assert emp_joined.json()['workspace_id'] == owner_ws
    emp_h = {'Authorization': 'Bearer ' + emp_joined.json()['access_token']}

    # Single-use: reusing the consumed link must return 410 Gone
    assert client.get(f'/api/invites/{emp_token}').status_code == 410
    assert client.post(
        '/api/invites/accept',
        json={
            'token': emp_token,
            'name': 'Second Try',
            'email': f'second-{suffix}@example.com',
            'password': 'AnotherPass123!',
        },
    ).status_code == 410

    # Employee cannot generate invite links (403)
    assert client.post(
        '/api/team/invite-links',
        headers=emp_h,
        json={'role': 'MEMBER', 'isolated': False},
    ).status_code == 403

    # 2. Owner generates an Isolated Friend Shareable Link
    friend_link = client.post(
        '/api/team/invite-links',
        headers=owner_h,
        json={'role': 'ADMIN', 'isolated': True, 'label': 'Friend Studio'},
    )
    assert friend_link.status_code == 201, friend_link.text
    friend_token = friend_link.json()['token']
    friend_joined = client.post(
        '/api/invites/accept',
        json={
            'token': friend_token,
            'name': 'Friend Link Boss',
            'email': f'friend-link-{suffix}@example.com',
            'password': 'FriendCustomPass9!',
        },
    )
    assert friend_joined.status_code == 201, friend_joined.text
    friend_ws = friend_joined.json()['workspace_id']
    assert friend_joined.json()['role'] == 'ADMIN'
    assert friend_ws != owner_ws
    friend_h = {'Authorization': 'Bearer ' + friend_joined.json()['access_token']}

    # Friend cannot create an Isolated Friend link for Owner or see Owner members
    assert client.post(
        '/api/team/invite-links',
        headers=friend_h,
        json={'role': 'ADMIN', 'isolated': True},
    ).status_code == 403
    assert all(m['email'] != owner_email for m in client.get('/api/members', headers=friend_h).json())

    # 3. Email-locked invite rejects wrong email (403) and revoked invite rejects (410)
    locked = client.post(
        '/api/team/invite-links',
        headers=owner_h,
        json={
            'role': 'MEMBER',
            'isolated': False,
            'target_email': f'exact-{suffix}@example.com',
        },
    )
    assert locked.status_code == 201
    assert client.post(
        '/api/invites/accept',
        json={
            'token': locked.json()['token'],
            'name': 'Wrong Person',
            'email': f'wrong-{suffix}@example.com',
            'password': 'Password123!',
        },
    ).status_code == 403

    assert client.delete(f'/api/team/invites/{locked.json()["id"]}', headers=owner_h).status_code == 200
    assert client.get(f'/api/invites/{locked.json()["token"]}').status_code == 410

    # 4. Owner can promote Employee -> ADMIN in workspace and demote back -> MEMBER
    emp_member_id = next(
        m['id'] for m in client.get('/api/members', headers=owner_h).json()
        if m['email'] == f'joined-emp-{suffix}@example.com'
    )
    assert client.put(f'/api/team/members/{emp_member_id}/role', headers=owner_h, json={'role': 'ADMIN'}).status_code == 200
    assert client.put(f'/api/team/members/{emp_member_id}/role', headers=owner_h, json={'role': 'MEMBER'}).status_code == 200


def test_initial_owner_bootstrap_and_https_media_cookie(client):
    suffix = uuid4().hex[:8]
    email = f'boot-{suffix}@example.com'
    bootstrap_initial_owner(email, 'BootPass123!', 'Cloud Owner')
    bootstrap_initial_owner(email, 'OtherPass999!', 'Cloud Owner')

    login_res = client.post('/api/auth/login', json={'email': email, 'password': 'BootPass123!'})
    assert login_res.status_code == 200
    assert login_res.json()['role'] == 'OWNER'

    headers = {'Authorization': 'Bearer ' + login_res.json()['access_token']}
    cookie_res = client.post(
        '/api/auth/media-session',
        headers={**headers, 'X-Forwarded-Proto': 'https'},
    )
    assert cookie_res.status_code == 200
    set_cookie = cookie_res.headers.get('set-cookie', '').lower()
    assert 'media_session=' in set_cookie
    assert 'samesite=none' in set_cookie
    assert 'secure' in set_cookie
    assert 'httponly' in set_cookie


def test_vault_incremental_check_existing_rescan_and_library_dedup(client, tmp_path):
    import io
    from fastapi import UploadFile
    from app.api.studio import upload_bulk
    from app.models import CelebrityAsset, LibraryMedia, MediaCollection, WorkspaceMember

    suffix = uuid4().hex[:8]
    owner_email = f'vault-owner-{suffix}@example.com'
    emp_email = f'vault-emp-{suffix}@example.com'
    bootstrap_initial_owner(owner_email, 'VaultPass123!', 'Vault Owner')
    owner_h = _login(client, owner_email, 'VaultPass123!')
    owner_me = client.get('/api/auth/me', headers=owner_h).json()

    emp_inv = client.post(
        '/api/team/invite',
        headers=owner_h,
        json={'name': 'Vault Emp', 'email': emp_email, 'role': 'MEMBER'},
    ).json()
    emp_h = _login(client, emp_email, emp_inv['temporary_password'])

    # Setup initial vault with one existing file + a lingering .tmp_ partial file
    vault = tmp_path / f'vault-sync-{suffix}'
    (vault / 'Stephen A. Smith').mkdir(parents=True)
    existing_bytes = b'\xff\xd8\xff\xe0' + b'A' * 120
    (vault / 'Stephen A. Smith' / 'react.jpg').write_bytes(existing_bytes)
    (vault / 'Stephen A. Smith' / '.tmp_deadbeef_partial.mp4').write_bytes(b'partial')

    conn = client.post('/api/assets/connect-folder', headers=owner_h, json={'folder_path': str(vault), 'preference': 'mix_both'})
    assert conn.status_code == 200, conn.text
    assert conn.json()['total_assets'] == 1  # .tmp_ ignored

    # Fast manifest lists normalized lowercase relative path -> byte size, ignoring .tmp_ files
    manifest = client.get('/api/assets/manifest', headers=owner_h)
    assert manifest.status_code == 200, manifest.text
    mdata = manifest.json()
    assert mdata['total'] == 1
    assert mdata['files'] == {'stephen a. smith/react.jpg': len(existing_bytes)}

    # Pre-check detects exact existing file (index 0) and ignores new/resized items
    chk = client.post(
        '/api/assets/check-existing',
        headers=owner_h,
        json={
            'celebrity_name': '',
            'items': [
                {'relative_path': 'MainFolder/Stephen A. Smith/react.jpg', 'size': len(existing_bytes)},
                {'relative_path': 'MainFolder/Stephen A. Smith/react.jpg', 'size': len(existing_bytes) + 5},
                {'relative_path': 'MainFolder/Kobe Bryant/clip1.mp4', 'size': 64},
            ],
        },
    )
    assert chk.status_code == 200, chk.text
    assert chk.json()['existing_indices'] == [0]

    # RBAC: employee cannot call check-existing or rescan
    assert client.post('/api/assets/check-existing', headers=emp_h, json={'items': []}).status_code == 403
    assert client.post('/api/assets/rescan', headers=emp_h, json={}).status_code == 403

    # Upload bulk directly: existing exact size skipped, new file atomically written, asset ID preserved after rescan
    with SessionLocal() as db:
        first_asset = db.query(CelebrityAsset).filter_by(workspace_id=owner_me['workspace_id']).one()
        orig_id = first_asset.id
        owner_member = db.query(WorkspaceMember).filter_by(user_id=owner_me['id'], workspace_id=owner_me['workspace_id']).one()
        res_bulk = upload_bulk(
            celebrity_name='',
            skip_scan=True,
            skip_existing=True,
            files=[
                UploadFile(file=io.BytesIO(existing_bytes), filename='MainFolder/Stephen A. Smith/react.jpg', size=len(existing_bytes)),
                UploadFile(file=io.BytesIO(b'new-clip-bytes'), filename='MainFolder/Kobe Bryant/clip1.mp4', size=14),
            ],
            context=(None, owner_member),
            db=db,
        )
        assert res_bulk['skipped'] == 1
        assert res_bulk['saved'] == 1

    rescan = client.post('/api/assets/rescan', headers=owner_h, json={'preference': 'mix_both'})
    assert rescan.status_code == 200
    assert rescan.json()['total_assets'] == 2

    with SessionLocal() as db:
        preserved = db.get(CelebrityAsset, orig_id)
        assert preserved is not None and preserved.file_name == 'react.jpg'

    # Media library collection check-existing matches existing image by name and exact byte size
    col_res = client.post('/api/library/collections', headers=owner_h, json={'name': f'Col-{suffix}', 'channel_id': None})
    assert col_res.status_code == 201
    col_id = col_res.json()['id']
    lib_file = tmp_path / f'lib-{suffix}.jpg'
    lib_bytes = b'lib-photo-content-12345'
    lib_file.write_bytes(lib_bytes)
    with SessionLocal() as db:
        db.add(LibraryMedia(
            id=new_id(), collection_id=col_id, name='sample.jpg', media_type='photo',
            creator='Owner', license='Own work', local_path=str(lib_file),
            content_hash=uuid4().hex, approved=True, archived=False,
        ))
        db.commit()

    lib_chk = client.post(
        f'/api/library/collections/{col_id}/check-existing',
        headers=owner_h,
        json={'items': [{'name': 'sample.jpg', 'size': len(lib_bytes)}, {'name': 'other.jpg', 'size': 10}]},
    )
    assert lib_chk.status_code == 200
    assert lib_chk.json()['existing_indices'] == [0]


def test_public_register_creates_isolated_workspace(client, tmp_path):
    suffix = uuid4().hex[:8]
    email_a = f'user-a-{suffix}@example.com'
    email_b = f'user-b-{suffix}@example.com'

    reg_a = client.post(
        '/api/auth/register',
        json={'name': 'Creator A', 'email': email_a, 'password': 'PasswordA123'},
    )
    assert reg_a.status_code == 201, reg_a.text
    data_a = reg_a.json()
    assert data_a['role'] == 'OWNER'
    assert data_a['access_token']
    headers_a = {'Authorization': f"Bearer {data_a['access_token']}"}

    # Duplicate email registration is rejected cleanly with 409
    dup = client.post(
        '/api/auth/register',
        json={'name': 'Dup A', 'email': email_a.upper(), 'password': 'PasswordA123'},
    )
    assert dup.status_code == 409

    # Creator B gets a completely separate isolated workspace
    reg_b = client.post(
        '/api/auth/register',
        json={'name': 'Creator B', 'email': email_b, 'password': 'PasswordB123'},
    )
    assert reg_b.status_code == 201, reg_b.text
    data_b = reg_b.json()
    assert data_b['role'] == 'OWNER'
    assert data_b['workspace_id'] != data_a['workspace_id']
    headers_b = {'Authorization': f"Bearer {data_b['access_token']}"}

    # Vault created in A's workspace is invisible to B
    vault_a = tmp_path / f'reg-vault-{suffix}'
    (vault_a / 'LeBron James').mkdir(parents=True)
    (vault_a / 'LeBron James' / 'dunk.mp4').write_bytes(b'fake-mp4-bytes-123')
    conn_a = client.post('/api/assets/connect-folder', headers=headers_a, json={'folder_path': str(vault_a), 'preference': 'mix_both'})
    assert conn_a.status_code == 200
    assert conn_a.json()['total_assets'] == 1

    man_b = client.get('/api/assets/manifest', headers=headers_b)
    assert man_b.status_code == 200
    assert man_b.json()['total'] == 0
    assert man_b.json()['files'] == {}
