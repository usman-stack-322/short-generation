import json
import httpx
import pytest
from app.ai.scripts import GeminiProvider, generate_script, generate_seo, FIELDS
from app.ai.reliability import GeminiGenerationError
from app.core.config import settings


@pytest.fixture(autouse=True)
def provider_config(monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','unit-secret-do-not-log')
    monkeypatch.setattr(settings,'gemini_model','primary-test-model')
    monkeypatch.setattr(settings,'gemini_fallback_model','')
    delays=[]
    monkeypatch.setattr('app.ai.reliability.time.sleep',delays.append)
    monkeypatch.setattr('app.ai.reliability.random.uniform',lambda *args:0)
    return delays


def success():
    content={field:'Original '+field for field in FIELDS}
    content['full_script']=' '.join(content.values())
    content['visual_keywords']=['football','stadium']
    content['scenes']=[{'visual_query':'football stadium','narration':'Original scene'} for _ in range(6)]
    return {'candidates':[{'content':{'parts':[{'text':json.dumps(content)}]}}]}


def responses(monkeypatch,codes):
    calls=[]
    def post(url,**kwargs):
        calls.append(url)
        code=codes[len(calls)-1]
        body=success() if code==200 else {'error':{'code':code,'status':'UNAVAILABLE' if code==503 else 'DENIED',
                                                   'message':'Provider detail unit-secret-do-not-log'}}
        return httpx.Response(code,json=body,request=httpx.Request('POST',url))
    monkeypatch.setattr('app.ai.scripts.httpx.post',post)
    return calls


def test_503_then_success(monkeypatch,provider_config):
    calls=responses(monkeypatch,[503,200])
    provider=GeminiProvider()
    result=provider.generate('30-second harmless script')
    assert result['full_script'] and len(result['scene_suggestions'])==6
    assert len(calls)==provider.retry_policy.attempts==2
    assert provider_config==[2]
    assert not provider.retry_policy.fallback_used


def test_503_exhaustion_is_retryable_not_authentication(monkeypatch,provider_config,caplog):
    calls=responses(monkeypatch,[503,503,503])
    provider=GeminiProvider()
    with pytest.raises(GeminiGenerationError,match='temporarily unavailable') as failure:
        provider.generate('test')
    assert failure.value.retryable
    assert len(calls)==3 and provider_config==[2,5]
    assert 'unit-secret-do-not-log' not in caplog.text
    assert '[REDACTED]' in caplog.text and '503' in caplog.text and 'UNAVAILABLE' in caplog.text


def test_optional_fallback_model_succeeds_once(monkeypatch,provider_config):
    monkeypatch.setattr(settings,'gemini_fallback_model','explicit-fallback-test-model')
    calls=responses(monkeypatch,[503,503,503,200])
    provider=GeminiProvider()
    provider.generate('test')
    assert provider.retry_policy.attempts==4
    assert provider.retry_policy.fallback_used
    assert provider.retry_policy.model_used=='explicit-fallback-test-model'
    assert all('primary-test-model:' in url for url in calls[:3])
    assert 'explicit-fallback-test-model:' in calls[-1]
    assert provider_config==[2,5]


@pytest.mark.parametrize('fallback_code',[503,404])
def test_optional_fallback_failure_is_not_retried(monkeypatch,provider_config,fallback_code):
    monkeypatch.setattr(settings,'gemini_fallback_model','explicit-fallback-test-model')
    calls=responses(monkeypatch,[503,503,503,fallback_code])
    provider=GeminiProvider()
    with pytest.raises(GeminiGenerationError):provider.generate('test')
    assert len(calls)==4 and provider_config==[2,5]
    assert provider.retry_policy.fallback_used


@pytest.mark.parametrize('code',[400,401,403,404,429])
def test_permanent_errors_are_not_retried_or_switched(monkeypatch,provider_config,code):
    monkeypatch.setattr(settings,'gemini_fallback_model','explicit-fallback-test-model')
    calls=responses(monkeypatch,[code])
    with pytest.raises(GeminiGenerationError) as failure:GeminiProvider().generate('test')
    assert len(calls)==1 and not provider_config and not failure.value.retryable


def test_malformed_response_retries_once_without_model_switch(monkeypatch,provider_config):
    monkeypatch.setattr(settings,'gemini_fallback_model','explicit-fallback-test-model')
    calls=[]
    def malformed(url,**kwargs):
        calls.append(url)
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'not JSON'}]}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr('app.ai.scripts.httpx.post',malformed)
    provider=GeminiProvider()
    with pytest.raises(GeminiGenerationError,match='invalid structured output'):provider.generate('test')
    assert len(calls)==2 and not provider_config and not provider.retry_policy.fallback_used


def test_live_script_failure_never_uses_demo(monkeypatch):
    responses(monkeypatch,[503,503,503])
    monkeypatch.setattr('app.ai.scripts._fallback_script',lambda *args,**kwargs:pytest.fail('Demo generation must never run'))
    with pytest.raises(GeminiGenerationError):generate_script('Career achievements','Cristiano Ronaldo','Clear',30)


def test_live_seo_failure_never_uses_derived_metadata(monkeypatch):
    calls=responses(monkeypatch,[503,503,503])
    with pytest.raises(GeminiGenerationError):generate_seo('Career achievements','Cristiano Ronaldo',{'full_script':'Test script'})
    assert len(calls)==3


def test_exhausted_live_job_is_failed_and_retryable(publishable,monkeypatch):
    responses(monkeypatch,[503,503,503])
    p=publishable
    response=p['client'].post(f"/api/videos/{p['job_id']}/regenerate",headers=p['owner'],json={'scope':'script'})
    assert response.status_code==200
    job=p['client'].get(f"/api/videos/{p['job_id']}",headers=p['owner']).json()
    assert job['status']=='failed' and job['failed_step']=='script_generation'
    assert job['retryable'] is True
    assert job['error_message']=='Gemini is temporarily unavailable because of high demand. Please retry generation.'
    assert 'unit-secret-do-not-log' not in json.dumps(job)


def test_script_requests_enforce_scene_schema_at_provider(monkeypatch):
    captured={}
    def post(url,**kwargs):
        captured.update(kwargs['json'])
        return httpx.Response(200,json=success(),request=httpx.Request('POST',url))
    monkeypatch.setattr('app.ai.scripts.httpx.post',post)
    result=GeminiProvider().generate('Structured script')
    schema=captured['generationConfig']['responseJsonSchema']
    assert schema['properties']['scenes']['minItems']==6
    assert schema['properties']['scenes']['maxItems']==12
    assert set(FIELDS)|{'full_script','scenes','visual_keywords'}==set(schema['required'])
    assert len(result['scene_suggestions'])==6


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
