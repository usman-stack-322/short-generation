import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from app.research.verification import verify_story,source_metadata,duplicate_signals
from app.research.live import assess


def report(title,host='bbc.com',summary='',**extra):
    return {'title':title,'summary':summary,'source_name':host,'source_domain':host,
            'source_url':'https://'+host+'/sport/report','published_at':datetime.now(timezone.utc).isoformat(),
            'reliability_score':.99,**extra}


def test_authoritative_single_source_low_risk_pass():
    row=report('Ronaldo reaches goals milestone','uefa.com')
    result=verify_story(row,[row])
    assert result['passed'] and result['risk_level']=='LOW'
    assert result['label']=='Single authoritative source' and result['independent_source_count']==1
    assert assess([row],'Ronaldo',[],[])[0]['status']=='verified'


def test_medium_risk_single_source_hold():
    row=report('Ronaldo performance analysis after international match')
    result=verify_story(row,[row])
    assert not result['passed'] and result['risk_level']=='MEDIUM'
    assert result['label']=='Needs second source'


def test_two_independent_sources_pass():
    a=report('Ronaldo 2028 contract update after match')
    b=report('Contract update for Ronaldo announced following match for 2028','espn.com')
    result=verify_story(a,[a,b])
    assert result['passed'] and result['independent_source_count']==2
    assert all(r['status']=='verified' for r in assess([a,b],'Ronaldo',[],[]))


def test_syndicated_duplicate_not_counted_twice():
    a=report('Ronaldo 2028 contract update confirmed',summary='Reuters: Club representatives confirmed the new contract today.')
    b=report('New 2028 contract update for Ronaldo','espn.com',summary='Reuters: The club provided details of an agreement.')
    result=verify_story(a,[a,b])
    assert not result['passed'] and result['independent_source_count']==1
    assert any('same originating wire/source' in entry['reasons'] for entry in result['duplicate_signals'])


def test_high_risk_one_source_block():
    row=report('Ronaldo suffers serious injury','uefa.com')
    result=verify_story(row,[row])
    assert not result['passed'] and result['risk_level']=='HIGH' and result['label']=='High-risk hold'


def test_high_risk_two_independent_sources_pass():
    a=report('Ronaldo suffers serious knee injury')
    b=report('Serious knee injury confirmed for Ronaldo','espn.com')
    result=verify_story(a,[a,b])
    assert result['passed'] and result['risk_level']=='HIGH' and result['label']=='Verified'
    assert all(row['status']=='verified' for row in assess([a,b],'Ronaldo',[],[]))


@pytest.mark.parametrize('signal', ['headline','summary','canonical','quote','publisher'])
def test_independence_signals(signal):
    a=report('Ronaldo contract update follows football meeting')
    b=report('Club representatives give Ronaldo contract update','espn.com')
    if signal=='headline': b['title']=a['title'].upper()
    if signal=='summary': a['summary']=b['summary']='The club provided a detailed account of the meeting and the latest developments surrounding Ronaldo today.'
    if signal=='canonical': a['canonical_url']='https://publisher.example/story?utm_source=a';b['canonical_url']='https://www.publisher.example/story?utm_source=b#section'
    if signal=='quote': a['summary']=b['summary']='The report said: "We have reviewed the details carefully and will publish a complete statement tomorrow".'
    if signal=='publisher': b['source_url']='https://bbc.co.uk/sport/another'
    assert duplicate_signals(a,b)
    assert verify_story(a,[a,b])['independent_source_count']==1


def test_unknown_source_cannot_claim_official_authority():
    row=report('Ronaldo reaches goals milestone','untrusted.example',source_category='official_primary',verified_identity=True,
               publisher_url='https://uefa.com/news')
    assert source_metadata(row)['category']=='unknown'
    assert not verify_story(row,[row])['passed']


def test_authority_requires_configured_primary_scope(tmp_path,monkeypatch):
    from app.core.config import settings
    path=tmp_path/'sources.json'
    path.write_text(json.dumps({'sources':[{'hosts':['club.example'],'category':'official_primary','publisher_group':'club',
        'verified_identity':True,'reliability':.95,'primary_paths':['/official/'],'authoritative_for':['match_result']}]}))
    monkeypatch.setattr(settings,'research_sources_file',str(path))
    row=report('Ronaldo scores in official match result','club.example')
    assert not verify_story(row,[row])['passed']
    row['source_url']='https://club.example/official/result'
    assert verify_story(row,[row])['passed']
    row['title']='Ronaldo wins official award'
    assert not verify_story(row,[row])['passed']


def test_conflicts_stale_and_rumors_still_hold():
    a=report('Ronaldo scores 2 goals in international match')
    b=report('International match ends with Ronaldo scoring 3 goals','espn.com')
    assert not verify_story(a,[a,b])['passed']
    b=report('Ronaldo did not suffer injury','espn.com')
    a=report('Ronaldo suffers injury')
    assert not verify_story(a,[a,b])['passed']
    b['published_at']=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    assert verify_story(a,[a,b])['independent_source_count']==1
    a=report('Ronaldo reportedly wins award','uefa.com')
    assert not verify_story(a,[a])['passed']
    peers=[report('Ronaldo wins award','bbc.com'),report('Official award goes to Ronaldo','espn.com')]
    assert not verify_story(a,[a,*peers])['passed']


def test_manual_review_cannot_bypass_policy(publishable):
    from app.database.session import SessionLocal
    from app.models import ResearchCandidate,VideoJob
    from app.core.security import new_id
    p=publishable
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id'])
        row=report('Ronaldo suffers serious injury')
        key=new_id()
        db.add(ResearchCandidate(id=key,channel_id=job.channel_id,personality_id=job.personality_id,title=row['title'],
                                status='verification_required',data=json.dumps({**row,'evidence':[row]})))
        db.commit()
    response=p['client'].post(f'/api/research/{key}/verify',headers=p['owner'],json={
        'confirmed':True,'note':'I have reviewed the source, but there is still only one independent source.'})
    assert response.status_code==409


@pytest.mark.parametrize('title,continues', [('Ronaldo reaches goals milestone',True),('Ronaldo suffers serious injury',False)])
def test_pipeline_uses_risk_policy_without_demo(publishable,monkeypatch,title,continues):
    from unittest.mock import Mock
    from app.core.config import settings
    from app.database.session import SessionLocal
    from app.models import VideoJob
    p=publishable
    with SessionLocal() as db:
        personality_id=db.get(VideoJob,p['job_id']).personality_id
        from app.models import Personality
        db.get(Personality,personality_id).name='Ronaldo'
        db.commit()
    monkeypatch.setattr(settings,'research_provider','rss')
    monkeypatch.setattr('app.research.live.RSSResearchProvider.candidates',lambda *args:[{**report(title,'uefa.com'),'published_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}])
    generator=Mock(side_effect=RuntimeError('Reached real script-generation stage'))
    monkeypatch.setattr('app.services.pipeline.generate_script',generator)
    monkeypatch.setattr('app.services.pipeline.research_topic',Mock(side_effect=AssertionError('Demo forbidden')))
    response=p['client'].post('/api/videos/generate',headers=p['owner'],json={
        'channel_id':p['channel_id'],'personality_id':personality_id,'topic_mode':'current'})
    assert response.status_code==201
    job=p['client'].get('/api/videos/'+response.json()['id'],headers=p['owner']).json()
    if continues:
        assert generator.call_count==1 and job['failed_step']=='script_generation'
        assert job['verification']['label']=='Single authoritative source'
        assert job['sources'][0]['url'].startswith('https://uefa.com/')
    else:
        assert generator.call_count==0 and job['status']=='verification_required'
        assert job['verification']['label']=='High-risk hold'


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
