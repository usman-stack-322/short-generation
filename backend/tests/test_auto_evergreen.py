import json
from datetime import datetime,timezone
from unittest.mock import Mock
from types import SimpleNamespace
import pytest
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import VideoJob,Channel,Personality,ResearchCandidate,Topic,GenerationRequest
from app.research.evergreen import research_evergreen,historical_claims,load_article,NO_FALLBACK,event_identity
from app.research.verification import verify_story
from test_research_continuation import prepare,run,story


def article(name='Ronaldo',year=2010,url='https://uefa.com/history/one'):
    sentence=f'{name} won the football Golden Boot award in {year}'
    return {'title':sentence,'summary':sentence,'article_title':name+' football career',
            'article_excerpt':sentence+'.','source_url':url,'source_name':'UEFA',
            'published_at':'2011-01-02T00:00:00+00:00','access_checked_at':datetime.now(timezone.utc).isoformat()}


def setup(p,monkeypatch,news=None):
    script,_=prepare(p,monkeypatch,[])
    monkeypatch.setattr(settings,'gemini_api_key','unit-test-placeholder')
    monkeypatch.setattr('app.services.pipeline.generate_seo',lambda *a,**k:{'title':'2010 historical fixture','description':'Historical test fixture.','hashtags':['#Test'],'keywords':['fixture'],'cover_text':'PAST MOMENT'})
    monkeypatch.setattr('app.services.automatic_research.research_live',lambda *a,**kw:news or [])
    monkeypatch.setattr('app.research.evergreen.EvergreenSearchProvider.discover',lambda *a:[{'title':'Ronaldo award','source_url':'https://uefa.com/history/one'}])
    monkeypatch.setattr('app.research.evergreen.load_article',lambda row,person:article(person.name))
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);channel=db.get(Channel,j.channel_id);channel.automatic_evergreen_fallback=True;channel.niche='Football';db.get(Personality,j.personality_id).category='Football';db.commit()
    return script


def test_no_news_selects_verified_evergreen_full_mock_pipeline(publishable,monkeypatch):
    p=publishable;script=setup(p,monkeypatch)
    result=run(p)
    assert result['status']=='ready_for_review' and result['script'] and result['video_url']
    assert result['content_type']=='historical' and result['verification_status']=='verified'
    assert result['fallback_reason'] and result['research_trace']['selected_candidate_id']
    assert result['sources'][0]['event_date']=='2010-01-01' and result['sources'][0]['event_date_precision']=='year'
    assert script.call_count==1 and json.loads(script.call_args.args[-1])['content_type']=='historical'
    assert result['approval_count']==0
    saved=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert saved['content_type']=='historical' and saved['script']==result['script']
    assert saved['scenes'][0]['caption'].startswith('2010')
    with SessionLocal() as db:
        selected=db.get(ResearchCandidate,result['research_trace']['selected_candidate_id'])
        assert selected.status=='selected' and db.get(Topic,db.get(VideoJob,p['job_id']).topic_id).event_identity


def test_fresh_news_keeps_news_path(publishable,monkeypatch):
    p=publishable;script=setup(p,monkeypatch)
    from app.research.live import research_live
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);candidates=research_live(db,db.get(Personality,j.personality_id),j.channel_id,Mock(candidates=Mock(return_value=[story()])))
    monkeypatch.setattr('app.services.automatic_research.research_live',lambda *a,**kw:candidates)
    fallback=Mock(side_effect=AssertionError('No evergreen when verified news exists'))
    monkeypatch.setattr('app.services.automatic_research.research_evergreen',fallback)
    result=run(p)
    assert result['status']=='ready_for_review' and result['content_type']=='news' and script.called and not fallback.called


def test_no_eligible_historical_holds_without_gemini(publishable,monkeypatch):
    p=publishable;script=setup(p,monkeypatch)
    monkeypatch.setattr('app.research.evergreen.load_article',lambda *a:article('Someone Else'))
    result=run(p)
    assert result['status']=='verification_required' and '1 accessible / 1 attempted' in result['error_message'] and 'direct public historical article URLs' in result['error_message'] and not script.called
    assert result['sources'][0]['reason'] and not result['video_url']


def test_disabled_and_manual_do_not_automatically_fallback(publishable,monkeypatch):
    p=publishable;script=setup(p,monkeypatch)
    fallback=Mock(side_effect=AssertionError('Must not enter fallback'))
    monkeypatch.setattr('app.services.automatic_research.automatic_topic',fallback)
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);db.get(Channel,j.channel_id).automatic_evergreen_fallback=False;db.commit()
    assert run(p)['status']=='verification_required' and not fallback.called and not script.called
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);j.status='researching';j.topic_mode='manual';j.manual_topic='Manual requested topic';db.get(Channel,j.channel_id).automatic_evergreen_fallback=True;db.commit()
    assert run(p)['status']=='verification_required' and not fallback.called


@pytest.mark.parametrize('name,category,sentence',[
    ('Stephen A. Smith','NBA','Stephen A. Smith joined a basketball broadcasting team in 2003'),
    ('Gilbert Arenas','NBA','Gilbert Arenas won a basketball award in 2003'),
    ("Gil’s Arena",'NBA',"Gil’s Arena launched a basketball show in 2023"),
    ('Apple','Business','Apple founded a computer company in 1976'),
    ('Muhammad Ali','Boxing','Muhammad Ali won a heavyweight boxing award in 1964')])
def test_personality_niche_and_initials_not_ronaldo_specific(name,category,sentence):
    person=SimpleNamespace(name=name,category=category,keywords='[]')
    a={**article(name),'article_excerpt':sentence+'.','article_title':name+' '+category}
    rows=historical_claims(a,person,SimpleNamespace(niche=category))
    assert len(rows)==1 and rows[0]['event_date_precision']=='year'
    assert not historical_claims(a,person,SimpleNamespace(niche='Unrelated Niche'))


def test_accessible_excerpt_not_search_snippet(monkeypatch):
    person=SimpleNamespace(name='Ronaldo',keywords='[]')
    monkeypatch.setattr('app.research.evergreen.public_get',Mock(return_value=(b'<h1>Unrelated football player</h1><p>No matching personality here.</p>',{})))
    with pytest.raises(ValueError,match='incidental'):load_article({'source_url':'https://bbc.com/sport/one','title':'Ronaldo award'},person)
    monkeypatch.setattr('app.research.evergreen.public_get',Mock(side_effect=TimeoutError()))
    with pytest.raises(TimeoutError):load_article({'source_url':'https://bbc.com/sport/one','title':'Ronaldo award'},person)


def test_duplicates_skip_to_next_historical_event(publishable,monkeypatch):
    p=publishable;setup(p,monkeypatch)
    first=run(p);assert first['status']=='ready_for_review'
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);j.topic=None;j.script=None;j.video=None;j.voice_generation=None;j.status='researching';db.commit()
    monkeypatch.setattr('app.research.evergreen.EvergreenSearchProvider.discover',lambda *a:[{'title':'Same event different headline','source_url':'https://uefa.com/history/old'},{'title':'Another award','source_url':'https://uefa.com/history/new'}])
    monkeypatch.setattr('app.research.evergreen.load_article',lambda row,person:article(person.name,2011 if row['source_url'].endswith('new') else 2010,row['source_url']))
    second=run(p)
    assert second['status']=='ready_for_review' and second['sources'][0]['event_date'].startswith('2011')


def test_historical_syndication_and_contradictions_not_verified():
    from app.research.evergreen import historical_claims
    person=SimpleNamespace(name='Apple',category='Business',keywords='[]')
    channel=SimpleNamespace(niche='Business')
    a=historical_claims({**article('Apple',1976,'https://bbc.com/business/a'),'article_excerpt':'Apple founded a computer company in California in 1976.'},person,channel)[0]
    b={**a,'source_url':'https://reuters.com/business/b','source_name':'Reuters','title':'In 1976, Apple founded a computer company in California','summary':'In 1976, Apple founded a computer company in California'}
    assert verify_story(a,[a,b],historical=True)['passed']
    a['originating_source']=b['originating_source']='Reuters'
    assert not verify_story(a,[a,b],historical=True)['passed']
    b['title']=b['summary']='Apple founded a computer company in California in 1977'
    assert not verify_story(a,[a,b],historical=True)['passed']


def test_channel_fallback_settings_persist_owner_only(owner_publishable):
    p=owner_publishable;url='/api/channels/'+p['channel_id']
    settings={'automatic_evergreen_fallback':True,'automatic_generation_enabled':False,'generation_duration':30,'niche':'Basketball'}
    assert p['client'].patch(url,headers=p['editor'],json=settings).status_code in (403,404)
    assert p['client'].patch(url,headers=p['owner'],json=settings).status_code==200
    saved=p['client'].get(url,headers=p['owner']).json()
    assert all(saved[k]==v for k,v in settings.items())


def test_daily_preparation_idempotent_and_upload_independent(publishable,monkeypatch):
    from app.services.preparation import prepare_due
    p=publishable;worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    with SessionLocal() as db:
        channel=db.get(Channel,p['channel_id']);channel.automatic_generation_enabled=True;channel.automatic_evergreen_fallback=True;channel.generation_duration=30;channel.default_language='es-ES';channel.daily_video_target=2;db.commit()
        before=db.query(VideoJob).count()
    now=datetime(2026,10,24,12,tzinfo=timezone.utc)
    prepare_due(now);prepare_due(now)
    assert worker.call_count==2
    with SessionLocal() as db:
        assert db.query(VideoJob).count()==before+2
        rows=db.query(VideoJob).filter_by(channel_id=p['channel_id'],duration=30,language_code='es-ES').all()
        assert len(rows)==2 and all(json.loads(j.research_trace)['generation_origin']=='daily_preparation' for j in rows)
        db.get(Channel,p['channel_id']).automatic_generation_enabled=False;db.commit()


def test_historical_framing_validated_no_mock(monkeypatch):
    from app.ai.scripts import generate_script
    context=json.dumps({'content_type':'historical','event_date':'2010-01-01','event_date_precision':'year',
                        'sources':[{'supported_excerpt':'Ronaldo won a football award in 2010.'}]})
    monkeypatch.setattr(settings,'gemini_api_key','unit-test-placeholder')
    provider=Mock();provider.retry_policy.model_used='unit fixture';monkeypatch.setattr('app.ai.scripts.GeminiProvider',lambda:provider)
    provider.generate.return_value={'full_script':'Breaking today, Ronaldo won an award in 2010.'}
    with pytest.raises(ValueError,match='Historical script'):generate_script('Historical topic','Ronaldo','natural',30,source_context=context)
    provider.generate.return_value={'full_script':'In 2010, Ronaldo won the football award.'}
    assert '2010' in generate_script('Historical topic','Ronaldo','natural',30,source_context=context)[0]['full_script']
    monkeypatch.setattr(settings,'gemini_api_key','')
    with pytest.raises(ValueError,match='demo fallback'):generate_script('Historical topic','Ronaldo','natural',30,source_context=context)



def test_news_windows_skip_inaccessible_without_repeated_access(publishable,monkeypatch):
    from app.research.live import research_live,RSSResearchProvider
    from app.services.automatic_research import automatic_topic
    p=publishable;setup(p,monkeypatch)
    class Windows:
        calls=[]
        def search_window(self,name,keywords,days,now):
            from datetime import timedelta
            self.calls.append(days)
            return [{**story(),'published_at':(now-timedelta(seconds=1)).isoformat()}]
    provider=Windows()
    monkeypatch.setattr('app.services.automatic_research.research_live',lambda db,person,channel,**kw:research_live(db,person,channel,provider,**kw))
    access=Mock(return_value=False);monkeypatch.setattr('app.services.automatic_research.news_access',access)
    result=run(p)
    assert result['content_type']=='historical' and provider.calls==[3,7,14] and access.call_count==1


def test_concurrent_daily_triggers_do_not_duplicate(publishable,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.services.preparation import prepare_due
    p=publishable;worker=Mock();monkeypatch.setattr('app.api.videos.run_job',worker)
    with SessionLocal() as db:
        c=db.get(Channel,p['channel_id']);c.automatic_generation_enabled=True;c.daily_video_target=1;db.commit();before=db.query(VideoJob).count()
    instant=datetime(2026,10,25,12,tzinfo=timezone.utc)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:prepare_due(instant),range(2)))
    with SessionLocal() as db:
        assert db.query(VideoJob).count()==before+1
        db.get(Channel,p['channel_id']).automatic_generation_enabled=False;db.commit()
    assert worker.call_count==1


def test_failed_render_keeps_historical_script_checkpoint(publishable,monkeypatch):
    p=publishable;script=setup(p,monkeypatch)
    monkeypatch.setattr('app.services.pipeline.render_video',Mock(side_effect=RuntimeError('Fixture render failure')))
    with pytest.raises(RuntimeError,match='render failure'):run(p)
    saved=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert saved['status']=='failed' and saved['failed_step']=='rendering' and saved['script'] and not saved['video_url']
    assert saved['content_type']=='historical' and script.call_count==1


def test_reference_list_validation_and_historical_publication_policy(monkeypatch):
    # Retrieval only accepts public HTTPS pages; no source age relaxation affects news.
    person=SimpleNamespace(name='Ronaldo',category='Football',keywords='[]')
    source=historical_claims(article(),person,SimpleNamespace(niche='Football'))[0]
    assert verify_story(source,[source],historical=True)['passed']
    assert not verify_story(source,[source])['passed']
    future={**source,'event_date':'2099-01-01'}
    assert not verify_story(future,[future],historical=True)['passed']


def test_event_identity_ignores_headline_figures_and_reporting_location():
    base={'title':'Cristiano Ronaldo won the 2008 Ballon d Or award in Paris','summary':'','subject':'Cristiano Ronaldo'}
    variant={**base,'title':'Cristiano Ronaldo received 446 votes for the 2008 Ballon d Or award in London'}
    assert event_identity(base)==event_identity(variant)
    assert event_identity(base)!=event_identity({**base,'title':'Cristiano Ronaldo won the 2013 Ballon d Or award'})


def test_reference_url_input_rejects_credentials_and_invalid_duration(publishable):
    p=publishable;url='/api/channels/'+p['channel_id']
    assert p['client'].patch(url,headers=p['owner'],json={'evergreen_source_urls':['https://user:password@example.com/article']}).status_code==422
    assert p['client'].patch(url,headers=p['owner'],json={'evergreen_source_urls':['file:///private']}).status_code==422
    assert p['client'].patch(url,headers=p['owner'],json={'generation_duration':31}).status_code==422


def test_distinct_events_from_same_profile_remain_available(publishable,monkeypatch):
    from app.research.evergreen import duplicate_story
    p=publishable;setup(p,monkeypatch);assert run(p)['status']=='ready_for_review'
    person=SimpleNamespace(name='Ronaldo',category='Football',keywords='[]')
    channel=SimpleNamespace(niche='Football')
    newer=historical_claims(article('Ronaldo',2011),person,channel)[0]
    with SessionLocal() as db:
        assert not duplicate_story(db,newer,p['channel_id'])
        same=historical_claims(article('Ronaldo',2010),person,channel)[0]
        assert duplicate_story(db,same,p['channel_id'])


def test_research_retry_uses_corrected_references_without_generating(publishable,monkeypatch):
    from test_review_drafts import held
    p=publishable;held(p)
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);j.research_trace=json.dumps({'generation_settings':{'evergreen_source_urls':'["https://uefa.com/old"]','duration':30,'voice':'en-US'}})
        c=db.get(Channel,p['channel_id']);c.automatic_evergreen_fallback=True;c.evergreen_source_urls='["https://uefa.com/new"]';db.commit()
    worker=Mock();monkeypatch.setattr('app.services.job_research.run_research_job',worker)
    script=Mock(side_effect=AssertionError('Research retry must not generate'))
    monkeypatch.setattr('app.services.pipeline.generate_script',script)
    response=p['client'].post('/api/videos/'+p['job_id']+'/research',headers=p['owner'])
    assert response.status_code==200,response.text
    snapshot=response.json()['research_trace']['generation_settings']
    assert snapshot['evergreen_source_urls']=='["https://uefa.com/new"]' and snapshot['duration']==30 and snapshot['voice']=='en-US'
    assert worker.call_count==1 and not script.called and response.json()['id']==p['job_id']


@pytest.mark.parametrize('text',[
 'In 2010, Ronaldo won an award after scoring 42 goals.',
 'In 2010, Ronaldo won an award because a coach changed his career.',
 'In 2010, Ronaldo won an award and he is the current captain.',
 'In 2010, Ronaldo said "I am the greatest footballer ever" after an award.',
 'In 2010, Ronaldo won an award and suffered a medical illness.'
])
def test_generated_historical_claims_cannot_expand_beyond_evidence(text):
    from app.research.grounding import validate_historical_claims
    with pytest.raises(ValueError):
        validate_historical_claims({'full_script':text},{'sources':[{'supported_excerpt':'Ronaldo won a football award in 2010.'}]})


def test_evergreen_bad_source_does_not_end_other_publishers(publishable,monkeypatch):
    from app.research.evergreen import research_evergreen
    import httpx
    p=publishable
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);person=db.get(Personality,j.personality_id);channel=db.get(Channel,j.channel_id)
        person.category='Football';channel.niche='Football';db.commit()
        rows=[{'title':'Failed source','source_url':'https://skysports.com/failed'},
              {'title':'Another failed article','source_url':'https://skysports.com/failed2'},
              {'title':'Independent official event','source_url':'https://uefa.com/verified'}]
        def load(row,persona):
            if 'skysports' in row['source_url']:raise httpx.ReadTimeout('temporary')
            return article(persona.name,url=row['source_url'])
        monkeypatch.setattr('app.research.evergreen.load_article',load)
        monkeypatch.setattr(settings,'evergreen_max_sources',2)
        result=research_evergreen(db,person,channel,Mock(discover=Mock(return_value=rows)))
        assert any(x.status=='verified' for x in result)
        assert result.diagnostics['attempted']==2
        assert result.diagnostics['budget_exhausted']
        assert any(x['status']=='network_failure' for x in result.diagnostics['outcomes'])


def test_unknown_duplicates_do_not_spend_article_access_budget(publishable,monkeypatch):
    p=publishable
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);person=db.get(Personality,j.personality_id);channel=db.get(Channel,j.channel_id)
        person.category='Football';channel.niche='Football';db.commit()
        rows=[{'title':'Unknown','source_url':'https://unknown.invalid/a'}]*3+[{'title':'Official','source_url':'https://uefa.com/story'}]
        load=Mock(side_effect=lambda row,persona:article(persona.name,url=row['source_url']))
        monkeypatch.setattr('app.research.evergreen.load_article',load);monkeypatch.setattr(settings,'evergreen_max_sources',1)
        result=research_evergreen(db,person,channel,Mock(discover=Mock(return_value=rows)))
        assert load.call_count==1 and any(x.status=='verified' for x in result)
        assert result.diagnostics['attempted']==1


def test_historical_fetch_bounded_retry_and_no_permission_retry(monkeypatch):
    import httpx
    from app.research.evergreen import research_fetch
    fn=Mock(side_effect=[httpx.ReadTimeout('temporary'),(b'ok',{})])
    monkeypatch.setattr('app.research.evergreen.public_get',fn);monkeypatch.setattr('app.research.evergreen.time.sleep',lambda _:None)
    assert research_fetch('https://uefa.com/story')[0]==b'ok' and fn.call_count==2
    response=httpx.Response(403,request=httpx.Request('GET','https://uefa.com/story'))
    fn=Mock(side_effect=httpx.HTTPStatusError('denied',request=response.request,response=response))
    monkeypatch.setattr('app.research.evergreen.public_get',fn)
    with pytest.raises(httpx.HTTPStatusError):research_fetch('https://uefa.com/story')
    assert fn.call_count==1


def test_press_association_copies_not_independent():
    from app.research.verification import duplicate_signals
    a={'title':'Ronaldo award 2008','summary':'Press Association report','source_url':'https://skysports.com/a'}
    b={'title':'Ronaldo historical accolade','summary':'PA Media report','source_url':'https://theguardian.com/b'}
    assert 'same originating wire/source' in duplicate_signals(a,b)


def test_discovery_does_not_truncate_alternatives_at_access_budget(monkeypatch):
    from app.research.evergreen import EvergreenSearchProvider
    person=SimpleNamespace(name='Cristiano Ronaldo',category='Football',keywords='[]',research_keywords='[]')
    channel=SimpleNamespace(niche='Football',default_language='en-US',evergreen_source_urls='["https://skysports.com/a","https://uefa.com/b"]')
    xml=b'<rss version="2.0"><channel><item><title>Cristiano Ronaldo historical award</title><link>https://theguardian.com/c</link></item></channel></rss>'
    monkeypatch.setattr(settings,'evergreen_max_sources',2)
    fetch=Mock(return_value=(xml,{}));monkeypatch.setattr('app.research.evergreen.research_fetch',fetch)
    provider=EvergreenSearchProvider();rows=provider.discover(person,channel)
    assert len(rows)==3 and rows[-1]['source_url']=='https://theguardian.com/c'
    assert fetch.call_count==4 and len(provider.diagnostics['searches'])==4
    assert any('site%3Atheguardian.com' in call.args[0] for call in fetch.call_args_list)


def test_aggregator_landing_page_has_actionable_reason(monkeypatch):
    person=SimpleNamespace(name='Ronaldo',keywords='[]')
    monkeypatch.setattr('app.research.evergreen.public_get',Mock(return_value=(b'<h1>Google News</h1><p>Top stories</p>',{})))
    with pytest.raises(ValueError,match='direct public article URL'):
        load_article({'source_url':'https://news.google.com/rss/articles/example','publisher_url':'https://bbc.com','title':'Ronaldo award'},person)


def test_historical_subject_cannot_be_previous_winner_or_runner_up():
    text="FC Barcelona forward Lionel Messi has won the 2009 Ballon d'Or award ahead of last year's winner Cristiano Ronaldo."
    a={**article(),'article_excerpt':text}
    channel=SimpleNamespace(niche='Football')
    assert not historical_claims(a,SimpleNamespace(name='Cristiano Ronaldo',keywords='[]'),channel)
    assert historical_claims(a,SimpleNamespace(name='Lionel Messi',keywords='[]'),channel)


def test_long_publisher_menu_cannot_hide_relevant_article_lead(monkeypatch):
    body=('<div>'+' Menu '*400+'</div><h1>Ronaldo award</h1><p>Cristiano Ronaldo won the football Golden Boot award in 2010.</p>').encode()
    monkeypatch.setattr('app.research.evergreen.public_get',Mock(return_value=(body,{})))
    person=SimpleNamespace(name='Cristiano Ronaldo',keywords='[]')
    result=load_article({'source_url':'https://skysports.com/football/example'},person)
    assert 'Menu' not in result['article_excerpt'] and 'Cristiano Ronaldo' in result['article_excerpt'][:1000]
    assert historical_claims(result,person,SimpleNamespace(niche='Football'))


def test_contemporaneous_last_night_uses_publication_year_only():
    person=SimpleNamespace(name='Thierry Henry',keywords='[]')
    a={**article(),'article_title':'Thierry Henry football award','article_excerpt':"Thierry Henry was named the English PFA's Player of the Year for the second season running last night.",'published_at':'2004-04-26T00:00:00+00:00'}
    row=historical_claims(a,person,SimpleNamespace(niche='Football'))[0]
    assert row['event_date']=='2004-01-01' and row['event_date_precision']=='year'
    assert row['event_date_basis']=='last_night_in_dated_report' and '[Publication year: 2004]' in row['supported_excerpt']
    assert not historical_claims({**a,'published_at':'2004-01-01T00:00:00+00:00'},person,SimpleNamespace(niche='Football'))


def test_named_award_can_be_paraphrased_as_won_without_allowing_match_results():
    from app.research.grounding import validate_historical_claims
    context={'sources':[{'supported_excerpt':'In 2004, Thierry Henry was named PFA Player of the Year.'}]}
    validate_historical_claims({'full_script':'In 2004, Thierry Henry won the PFA Player of the Year award.'},context)
    with pytest.raises(ValueError,match='unsupported claim categories'):
        validate_historical_claims({'full_script':'In 2004, Thierry Henry won the PFA Player of the Year award and scored goals.'},context)


def test_time_budget_reports_hold_without_source_fetch(publishable,monkeypatch):
    p=publishable
    with SessionLocal() as db:
        j=db.get(VideoJob,p['job_id']);person=db.get(Personality,j.personality_id);channel=db.get(Channel,j.channel_id)
        load=Mock();monkeypatch.setattr('app.research.evergreen.load_article',load)
        monkeypatch.setattr('app.research.evergreen.time.monotonic',Mock(side_effect=[0,151]))
        result=research_evergreen(db,person,channel,SimpleNamespace(discover=lambda *a:[{'title':'Source','source_url':'https://uefa.com/a'}]))
        assert result==[] and not load.called
        assert result.diagnostics['outcome']=='budget_exhausted' and result.diagnostics['remaining_unattempted']==1


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
