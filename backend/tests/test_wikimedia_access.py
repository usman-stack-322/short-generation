"""All HTTP responses are local fixtures; no test may contact Wikimedia."""
import importlib.util
import json
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from email.utils import format_datetime
from pathlib import Path
import httpx
import pytest
from app.services.assets import wikimedia as wm
from app.services.assets import licensed
from app.core import network


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(wm.settings,'generated_dir',tmp_path)
    monkeypatch.setattr(wm.settings,'wikimedia_operator_contact','operator@unit-fixture.org')
    monkeypatch.setattr(wm.settings,'wikimedia_cache_seconds',900)
    monkeypatch.setattr(wm,'LOCK_DIR',tmp_path/'locks')
    monkeypatch.setattr(wm,'public_get',lambda *a,**k:pytest.fail('Live network forbidden in tests'))
    wm._holds.clear()
    yield
    wm._holds.clear()


def error(status,body='Provider error',headers=None):
    response=httpx.Response(status,content=body.encode(),headers=headers,request=httpx.Request('GET','https://commons.wikimedia.org/w/api.php'))
    return httpx.HTTPStatusError('fixture',request=response.request,response=response)


def helper():
    spec=importlib.util.spec_from_file_location('photo_helper',Path(__file__).resolve().parents[1]/'tools/photo_acceptance.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def test_actual_wire_headers_for_search_preflight_and_download(monkeypatch):
    seen=[];real_client=httpx.Client
    def handler(request):
        seen.append(request)
        return httpx.Response(200,content=b'{"query":{"pages":{},"general":{"sitename":"Commons"}}}' if request.url.path.endswith('api.php') else b'photo bytes')
    monkeypatch.setattr(network,'validate_url',lambda *a,**k:True)
    monkeypatch.setattr(network.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    monkeypatch.setattr(wm,'public_get',network.public_get)
    licensed.CommonsAssetProvider().search('football stadium photograph')
    wm.fetch('https://commons.wikimedia.org/w/api.php?action=query&format=json&meta=siteinfo')
    wm.fetch('https://upload.wikimedia.org/test.jpg')
    assert len(seen)==3
    assert all(r.headers['User-Agent']=='ShortsEnginePhotoBot/1.0 (operator@unit-fixture.org)' for r in seen)
    assert all(r.url.params.get('maxlag')=='5' for r in seen[:2])


@pytest.mark.parametrize('contact',['','name@example.com','name@unit.invalid','https://example.org','https://localhost','not a contact','email\r\nInjected: true'])
def test_missing_or_placeholder_contact_never_sent(contact,monkeypatch):
    monkeypatch.setattr(wm.settings,'wikimedia_operator_contact',contact)
    monkeypatch.setattr(wm.settings,'network_user_agent','AIShortsPlatform/0.2 (local user-operated research)')
    with pytest.raises(wm.WikimediaConfigurationError):wm.fetch('https://commons.wikimedia.org/w/api.php')


def test_existing_operator_contact_reused(monkeypatch):
    monkeypatch.setattr(wm.settings,'wikimedia_operator_contact','')
    monkeypatch.setattr(wm.settings,'network_user_agent','ExistingApp/2.0 (https://my-operator-site.org/contact)')
    assert wm.user_agent()=='ShortsEnginePhotoBot/1.0 (https://my-operator-site.org/contact)'


def test_403_retains_message_reference_and_suppresses_repeat_queries(monkeypatch):
    calls=[]
    def deny(*a,**k):calls.append(1);raise error(403,'<h1>Please respect our robot policy</h1><p>Reference shown: 768589d</p>')
    monkeypatch.setattr(wm,'public_get',deny)
    for query in ('first','different'):
        with pytest.raises(wm.WikimediaAccessError) as caught:wm.fetch('https://commons.wikimedia.org/w/api.php',params={'search':query})
        exc=caught.value
        assert exc.status_code==403 and exc.reference=='768589d'
        assert 'Please respect our robot policy' in licensed.failure_note(exc)
        assert 'DNS' not in licensed.failure_note(exc)
        assert helper().diagnostic_error(exc)['kind']=='provider_access_denied'
        wm._holds.clear()  # A second process/helper also observes persisted hold.
    assert len(calls)==1
    assert not list((wm.settings.generated_dir/'cache').glob('wikimedia/*.json'))


def test_streamed_error_body_is_retained_and_bounded(monkeypatch):
    real_client=httpx.Client
    monkeypatch.setattr(network,'validate_url',lambda *a,**k:True)
    monkeypatch.setattr(network.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(lambda request:httpx.Response(403,content=b'Reference: 768589d '+b'x'*20000)),**kwargs))
    with pytest.raises(httpx.HTTPStatusError) as caught:network.public_get('https://commons.wikimedia.org/w/api.php')
    assert len(caught.value.response.content)==8192 and '768589d' in caught.value.response.text


def test_cache_and_concurrent_request_serialization(monkeypatch):
    calls=[];active=0;maximum=0;guard=threading.Lock()
    def get(*a,**k):
        nonlocal active,maximum
        with guard:active+=1;maximum=max(active,maximum);calls.append(k)
        time.sleep(.02)
        with guard:active-=1
        return b'{"query":{}}',{}
    monkeypatch.setattr(wm,'public_get',get)
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda _:wm.fetch('https://commons.wikimedia.org/w/api.php',params={'action':'query'}),range(3)))
    assert len(calls)==1
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda n:wm.fetch('https://commons.wikimedia.org/w/api.php',params={'q':n}),range(3)))
    assert len(calls)==4 and maximum==1


def test_short_retry_after_then_success(monkeypatch):
    calls=[];delays=[]
    def get(*a,**k):
        calls.append(1)
        if len(calls)==1:raise error(503,headers={'Retry-After':'0'})
        return b'{"query":{}}',{}
    monkeypatch.setattr(wm,'public_get',get);monkeypatch.setattr(wm.time,'sleep',delays.append)
    wm.fetch('https://commons.wikimedia.org/w/api.php')
    assert len(calls)==2 and delays==[0]


@pytest.mark.parametrize('status',[403,429,503])
def test_long_retry_after_no_early_repeat(status,monkeypatch):
    calls=[]
    def get(*a,**k):calls.append(1);raise error(status,headers={'Retry-After':format_datetime(datetime.now(timezone.utc)+timedelta(seconds=600))})
    monkeypatch.setattr(wm,'public_get',get)
    for _ in range(2):
        with pytest.raises(wm.WikimediaAccessError):wm.fetch('https://commons.wikimedia.org/w/api.php')
    assert len(calls)==1


def test_401_not_retried(monkeypatch):
    calls=[]
    def get(*a,**k):calls.append(1);raise error(401)
    monkeypatch.setattr(wm,'public_get',get)
    with pytest.raises(wm.WikimediaAccessError):wm.fetch('https://commons.wikimedia.org/w/api.php')
    assert calls==[1]


def test_dns_tls_and_denial_are_different():
    h=helper()
    assert h.diagnostic_error(socket.gaierror(11001,'lookup failed'))['kind']=='dns_failure'
    assert h.diagnostic_error(ssl.SSLError('CERTIFICATE_VERIFY_FAILED'))['kind']=='tls_failure'
    assert 'TLS verification failed' in licensed.failure_note(ssl.SSLError('CERTIFICATE_VERIFY_FAILED'))
    assert h.diagnostic_error(wm.WikimediaAccessError(403,'Please respect our robot policy Reference: 768589d'))['reference']=='768589d'


def test_diagnostic_preflight_uses_identified_transport_and_stops_on_denial(monkeypatch):
    h=helper();calls=[]
    monkeypatch.setattr(h,'check_dns',lambda host:{'ok':True,'addresses':['8.8.8.8']})
    def deny(*a,**k):calls.append(k['user_agent']);raise error(403,'Please respect our robot policy Reference: 768589d')
    monkeypatch.setattr(wm,'public_get',deny)
    result=h.diagnose(live_check=True)
    assert len(calls)==1 and calls[0]==wm.user_agent()
    assert result['https'][0]['tls_connected'] and not result['commons_api']['ok']
    assert result['commons_api']['error']['reference']=='768589d'


def test_live_check_bypasses_success_cache_not_provider_hold(monkeypatch):
    calls=[]
    monkeypatch.setattr(wm,'public_get',lambda *a,**k:(calls.append(k) or b'{"query":{}}',{}))
    wm.fetch('https://commons.wikimedia.org/w/api.php')
    cached=wm.fetch('https://commons.wikimedia.org/w/api.php')
    assert cached[1]['X-AIShorts-Cache']=='hit' and len(calls)==1
    wm.fetch('https://commons.wikimedia.org/w/api.php',refresh=True)
    assert len(calls)==2 and all('refresh' not in k for k in calls)


def test_search_bounded_pool_keeps_license_gate(monkeypatch):
    calls=[]
    def get(url,**kwargs):
        calls.append(kwargs['params'])
        return json.dumps({'query':{'pages':{'1':{'title':'Ronaldo photo','imageinfo':[{'mime':'image/jpeg','descriptionurl':'https://commons.wikimedia.org/wiki/File:Photo','url':'https://upload.wikimedia.org/test.jpg','extmetadata':{'LicenseShortName':{'value':'CC BY-SA 4.0'},'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/4.0/'},'Artist':{'value':'Creator'}}}]}}}}).encode(),{}
    monkeypatch.setattr(wm,'public_get',get)
    assert licensed.CommonsAssetProvider().search('Cristiano Ronaldo photograph')==[]
    assert calls[0]['gsrlimit']==20 and calls[0]['gsrsearch']=='Cristiano Ronaldo'


def test_subject_disambiguation_requires_unique_category_match(monkeypatch):
    rows=[{'id':'Q11571','label':'Cristiano Ronaldo','description':'Portuguese association football player'},
          {'id':'Q933048','label':'Cristiano Ronaldo','description':'Major League Baseball player'}]
    monkeypatch.setattr(licensed,'fetch',lambda *a,**k:(json.dumps({'search':rows}).encode(),{}))
    provider=licensed.CommonsAssetProvider()
    assert provider.subject('Cristiano Ronaldo') is None
    assert provider.subject('Cristiano Ronaldo','Football')=='Q11571'
    assert provider.subject('Cristiano Ronaldo','Celebrities') is None
    assert provider.subject('Cristiano Ronaldo','Boxing') is None
    rows.append({'id':'Qother','label':'Cristiano Ronaldo','description':'Another football player'})
    assert provider.subject('Cristiano Ronaldo','Football') is None


def test_camera_evidence_does_not_override_identity_or_synthetic_exclusion():
    from app.services.assets.policy import photo_supported,matches_subject
    base={'source':'commons','title':'A stadium','description':'Documented scene','camera_make':'Canon','camera_model':'EOS'}
    assert photo_supported(base)
    assert not photo_supported({**base,'camera_model':None})
    assert not photo_supported({**base,'description':'AI-generated scene'})
    assert not matches_subject(base,'Cristiano Ronaldo')


def test_api_maxlag_does_not_misreport_http_status(monkeypatch):
    monkeypatch.setattr(wm,'public_get',lambda *a,**k:(b'{"error":{"code":"maxlag","info":"Waiting for replication"}}',{'Retry-After':'5'}))
    with pytest.raises(wm.WikimediaAccessError) as caught:wm.fetch('https://www.wikidata.org/w/api.php')
    assert caught.value.status_code==200 and caught.value.api_code=='maxlag'
    details=helper().diagnostic_error(caught.value)
    assert details['http_status']==200 and details['api_code']=='maxlag' and details['kind']=='provider_api_error'


def test_reference_retained_even_after_message_excerpt():
    exc=wm.WikimediaAccessError(403,'Please respect our robot policy '+('x'*2000)+' Reference: 768589d')
    assert exc.reference=='768589d' and '768589d' in str(exc)


def test_transport_reset_preserves_request_and_suppresses_scene_storm(monkeypatch):
    calls=[]
    def reset(*a,**k):
        calls.append(k)
        raise httpx.ConnectError('[WinError 10054] connection forcibly closed')
    monkeypatch.setattr(wm,'public_get',reset);monkeypatch.setattr(wm.time,'sleep',lambda _:None)
    for query in ['first','second']:
        with pytest.raises(wm.WikimediaTransportError) as caught:
            wm.fetch('https://commons.wikimedia.org/w/api.php',params={'action':'query','search':query})
        assert caught.value.status_code is None and caught.value.failure_kind=='connection_reset'
        assert 'search=first' in caught.value.request_url
        assert helper().diagnostic_error(caught.value)['http_status'] is None
        wm._holds.clear()  # the persistent hold also protects a restarted worker
    assert len(calls)==2 and all(row['timeout']==10 for row in calls)


def test_transport_hold_does_not_block_independent_image_host(monkeypatch):
    def get(url,**k):
        if 'commons.wikimedia.org' in url:raise httpx.ReadTimeout('fixture timeout')
        return b'image bytes',{}
    monkeypatch.setattr(wm,'public_get',get);monkeypatch.setattr(wm.time,'sleep',lambda _:None)
    with pytest.raises(wm.WikimediaTransportError):wm.fetch('https://commons.wikimedia.org/w/api.php')
    assert wm.fetch('https://upload.wikimedia.org/photo.jpg')[0]==b'image bytes'
