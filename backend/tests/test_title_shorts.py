import copy,json,hashlib,wave,struct
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.services import title_shorts as service
from app.services import title_research as retrieval
from app.api import title_shorts as routes
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import TitleShortDraft,WorkspaceMember


def plan_fixture():
    lines=['How did an idea become a research field? This short follows one narrow question about the early proposal.',
        'Researchers proposed studying how machines could use language and solve problems. The proposal described a research project, rather than a complete history.',
        'That distinction matters: the document offered a research direction. Read the original proposal to see what its authors actually suggested.']
    return {'scenes':[{'narration':s,'on_screen_text':'A research question','visual_description':'An illustrative campus photograph','image_query':'Dartmouth campus photograph','ai_image_prompt':'Editorial illustration of a research meeting, not archival evidence','motion':'push_in','transition':'dissolve'} for s in lines],
        'claims':[{'claim':'A proposal described a research project.','source_id':'S1','supporting_excerpt':'The proposal described a research project.'}]}

SOURCES=[{'id':'S1','url':'https://example.edu/history','title':'Fixture primary source','excerpt':'The proposal described a research project. Researchers proposed studying how machines could use language and solve problems.'},
    {'id':'S2','url':'https://example.gov/history','title':'Fixture independent source','excerpt':'A document offered a research direction.'}]


def draft_fixture():
    return SimpleNamespace(duration=45,language='English',style='educational',data=json.dumps({'analysis':{'angle':'The original research proposal'}}))


def test_no_key_is_an_explicit_configuration_error(monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','')
    with pytest.raises(ValueError,match='Configure GEMINI_API_KEY'):service.ai('Topic',service.Analysis)


def test_fetch_failure_never_claims_research(monkeypatch):
    monkeypatch.setattr(retrieval,'public_get',lambda *a,**k: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(ValueError,match='Search failed|Evidence insufficient'):service.research({'search_queries':['test']})


def test_sources_must_be_actual_accessible_pages_from_two_domains(monkeypatch):
    rss=b'<rss><channel><item><title>AI beginning research</title><link>https://alpha.edu/history</link></item><item><title>AI beginning research</title><link>https://beta.gov/history</link></item></channel></rss>'
    page=('<html><title>Real fetched fixture</title><h1>Research</h1><p>'+('A research proposal and its original authors. '*25)+'</p></html>').encode()
    def fetch(url,**kw):return (rss,{'content-type':'application/rss+xml'}) if 'bing' in url else (page.replace(b'original authors',b'original authors' if 'alpha.edu' in url else b'distinct contemporary researchers explain the founding document with different contextual evidence and phrasing').replace(b'A research proposal and its',b'A research proposal and its' if 'alpha.edu' in url else b'A completely independent historical account describes the'),{'content-type':'text/html'})
    monkeypatch.setattr(retrieval,'public_get',fetch)
    sources=service.research({'search_queries':['AI beginning']})
    assert len(sources)==2 and all(s['excerpt'] for s in sources)
    assert sources[0]['url']=='https://alpha.edu/history'


def test_source_snippets_are_not_sufficient(monkeypatch):
    rss=b'<rss><channel><item><link>https://alpha.edu/history</link><description>Search snippet is not evidence</description></item></channel></rss>'
    monkeypatch.setattr(retrieval,'public_get',lambda *a,**k:(rss,{'content-type':'application/rss+xml'}))
    with pytest.raises(ValueError,match='Search failed|Evidence insufficient'):service.research({'search_queries':['test']})


def test_fabricated_source_excerpt_is_rejected():
    plan=plan_fixture();plan['claims'][0]['supporting_excerpt']='A made up quotation absent from every source.'
    with pytest.raises(ValueError,match='supporting excerpt'):service.check_plan(draft_fixture(),plan,SOURCES,verify=False)


def test_factual_edit_must_pass_second_source_audit(monkeypatch):
    monkeypatch.setattr(service,'ai',lambda *args:{'supported':False,'reason':'A new date is not supported by the sources.'})
    with pytest.raises(ValueError,match='Source review failed'):service.check_plan(draft_fixture(),plan_fixture(),SOURCES)


def test_scenes_cover_full_script_and_selected_duration(monkeypatch):
    monkeypatch.setattr(service,'ai',lambda *args:{'supported':True,'reason':'Fixture paraphrase supported.'})
    plan=service.check_plan(draft_fixture(),plan_fixture(),SOURCES)
    assert plan['scenes'][0]['start']==0 and plan['scenes'][-1]['end']==44.4
    assert all(a['end']==b['start'] for a,b in zip(plan['scenes'],plan['scenes'][1:]))
    assert len(plan['scenes'])==3


@pytest.mark.parametrize('language,text',[('Urdu','English only text ' *25),('Roman Urdu','اردو زبان میں متن '*20)])
def test_script_writing_system_is_enforced(language,text):
    draft=draft_fixture();draft.language=language;plan=plan_fixture()
    for s in plan['scenes']:s['narration']=text
    with pytest.raises(ValueError):service.check_plan(draft,plan,SOURCES,verify=False)


@pytest.mark.parametrize('duration',[30,45,60])
@pytest.mark.parametrize('language',['English','Urdu','Roman Urdu'])
def test_input_duration_language_matrix(duration,language):
    assert service.TitleInput(title='A sufficiently specific topic',duration=duration,language=language).duration==duration


def test_routes_preserve_review_boundary_and_stale_write_protection(publishable,monkeypatch):
    ctx=publishable;client=ctx['client'];headers=ctx['owner'];called=[]
    monkeypatch.setattr(settings,'gemini_api_key','fixture-only-key')
    monkeypatch.setattr(routes,'work',lambda *a:called.append(a))
    response=client.post('/api/title-shorts',headers=headers,json={'title':'The Complete History of Artificial Intelligence','duration':45,'language':'English','style':'educational'})
    assert response.status_code==201;row=response.json();id=row['id']
    assert called[-1][1]=='prepare' and row['video_url'] is None
    assert client.post('/api/title-shorts/'+id+'/render',headers=headers,json={'revision':1}).status_code==409
    with SessionLocal() as db:
        saved=db.get(TitleShortDraft,id);saved.status='script_review';saved.data=json.dumps({'analysis':{'angle':'One proposal'},'sources':SOURCES,'plan':service.check_plan(draft_fixture(),plan_fixture(),SOURCES,verify=False),'assets':[None]*3});db.commit()
    texts=[s['narration'] for s in plan_fixture()['scenes']]
    saved=client.put('/api/title-shorts/'+id+'/script',headers=headers,json={'revision':1,'narrations':texts})
    assert saved.status_code==200 and saved.json()['revision']==2
    assert client.put('/api/title-shorts/'+id+'/script',headers=headers,json={'revision':1,'narrations':texts}).status_code==409
    rendered=client.post('/api/title-shorts/'+id+'/render',headers=headers,json={'revision':2})
    assert rendered.status_code==202 and called[-1][1]=='render'
    assert client.post('/api/title-shorts/'+id+'/render',headers=headers,json={'revision':3}).status_code==409
    assert rendered.json()['uploads_enabled'] is False
    assert client.get('/api/title-shorts/'+id,headers=ctx['editor']).status_code==404
    assert client.get('/api/title-shorts/'+id).status_code==401


def test_invalid_edit_does_not_mutate_revision(publishable):
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(role='OWNER').first()
        row=TitleShortDraft(id='edit-rejection-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='Fixture focused topic',duration=45,language='English',style='educational',status='script_review',data=json.dumps({'sources':SOURCES,'plan':plan_fixture(),'assets':[None]*3}))
        db.add(row);db.commit()
    r=publishable['client'].put('/api/title-shorts/edit-rejection-fixture/script',headers=publishable['owner'],json={'revision':1,'narrations':['Too short.']*3})
    assert r.status_code==422
    with SessionLocal() as db:assert db.get(TitleShortDraft,'edit-rejection-fixture').revision==1


def test_worker_stops_at_script_review_without_visual_or_speech_calls(publishable,monkeypatch):
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(role='OWNER').first()
        row=TitleShortDraft(id='prepare-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='History of AI',duration=45,language='English',style='educational',status='analyzing',data='{}');db.add(row);db.commit()
    def ai(prompt,schema):
        if schema==service.Analysis:return {'topic':'AI','viewer_intent':'Understand one origin story','angle':'One original proposal','rationale':'A focused story fits the short','search_queries':['AI original proposal']}
        if schema==service.Plan:return plan_fixture()
        return {'supported':True,'reason':'Fixture source review passed.'}
    monkeypatch.setattr(service,'ai',ai);monkeypatch.setattr(service,'research',lambda *a:copy.deepcopy(SOURCES))
    monkeypatch.setattr(service,'generate_narration',lambda *a,**k:pytest.fail('Speech must await explicit review'))
    monkeypatch.setattr(service,'collect_one',lambda *a,**k:pytest.fail('Visuals must await explicit review'))
    service.work('prepare-fixture')
    with SessionLocal() as db:
        row=db.get(TitleShortDraft,'prepare-fixture');assert row.status=='script_review' and json.loads(row.data)['sources']


def test_scene_regeneration_cannot_change_narration(publishable,monkeypatch):
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(role='OWNER').first();row=TitleShortDraft(id='scene-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='History of AI',duration=45,language='English',style='educational',status='visuals',data=json.dumps({'analysis':{},'plan':service.check_plan(draft_fixture(),plan_fixture(),SOURCES,verify=False),'assets':[None]*3}));db.add(row);db.commit()
    proposal=plan_fixture()['scenes'][0];proposal['narration']='Changed factual narration'
    monkeypatch.setattr(service,'ai',lambda *a:proposal)
    service.work('scene-fixture','scene',1)
    with SessionLocal() as db:
        row=db.get(TitleShortDraft,'scene-fixture');assert row.status=='failed';assert json.loads(row.data)['plan']['scenes'][0]['narration']!=proposal['narration']


def test_real_renderer_and_authenticated_download_with_explicit_audio_fixture(publishable,monkeypatch):
    """Real FFmpeg integration; synthetic test audio is NEVER a production success."""
    import math,array,re
    from PIL import Image
    from app.models import UploadTask
    from app.video.renderer import render_video
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(role='OWNER').first()
        row=TitleShortDraft(id='real-render-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='Isolated render contract fixture',duration=30,language='English',style='educational',status='validating',data='{}')
        folder=Path(settings.generated_dir)/'title-shorts'/row.id;folder.mkdir(parents=True)
        assets=[]
        for i,color in enumerate(['#2a4c70','#436d32','#835a33']):
            p=folder/f'fixture-{i}.jpg';Image.new('RGB',(500,700),color).save(p)
            assets.append({'path':str(p),'hash':hashlib.sha256(p.read_bytes()).hexdigest(),'credit':'Explicit test-only original image','source_url':'https://example.edu/fixture','license':'Test fixture','creator':'Test'})
        plan=plan_fixture();plan=service.check_plan(SimpleNamespace(duration=30,language='English',style='educational',data='{}'),plan,SOURCES,verify=False)
        row.data=json.dumps({'analysis':{'topic':'Fixture','angle':'One research proposal'},'plan':plan,'sources':SOURCES,'assets':assets});db.add(row);db.commit()
    def fixture_narration(text,voice,path,**kw):
        values=array.array('h',(int(7000*math.sin(2*math.pi*220*i/16000)) for i in range(25*16000)))
        with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(values.tobytes())
        tokens=list(re.finditer(r'\S+',text));words=[{'char':m.start(),'length':len(m.group()),'text':m.group(),'start':i*25/len(tokens),'end':(i+1)*25/len(tokens)} for i,m in enumerate(tokens)]
        path.with_suffix('.words.json').write_text(json.dumps({'provider':'Explicit synthetic integration fixture; NOT speech','audio_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(text.encode()).hexdigest(),'duration':25,'words':words}))
        kw['metadata'].update(voice='test-only fixture',locale='en-US')
    monkeypatch.setattr(service,'ai',lambda *a:{'supported':True,'reason':'Explicit fixture audit, not real research.'})
    monkeypatch.setattr(service,'generate_narration',fixture_narration)
    service.work('real-render-fixture','render')
    with SessionLocal() as db:
        row=db.get(TitleShortDraft,'real-render-fixture');assert row.status=='ready',row.error_message
        data=json.loads(row.data);video=Path(data['video']['path']);assert video.is_file();assert len(data['renders'])==1
        assert db.query(UploadTask).filter_by(job_id=row.id).count()==0
        assert 'Dialogue:' in (video.parent/'captions.ass').read_text()
    client=publishable['client'];headers=publishable['owner']
    cookie=client.post('/api/auth/media-session',headers=headers);assert cookie.status_code==200
    assert any('/api/title-shorts' in h for h in cookie.headers.get_list('set-cookie'))
    url='/api/title-shorts/real-render-fixture/media/video?revision=1'
    response=client.get(url);assert response.status_code==200
    assert hashlib.sha256(response.content).hexdigest()==data['video']['sha256']
    assert client.get(url,headers={'Range':'bytes=0-99'}).status_code==206
    assert client.get(url.replace('revision=1','revision=999')).status_code==404
    assert client.get(url+'&download=true').headers['content-disposition'].startswith('attachment')
    assert client.get(url.replace('/video?','/credits?')).status_code==200
    assert client.get(url.replace('/video?','/sources?')).status_code==200


def test_native_timing_and_speech_failure_never_yield_completed_video(publishable,monkeypatch):
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(role='OWNER').first()
        row=TitleShortDraft(id='speech-fail-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='One focused topic',duration=45,language='Urdu',style='educational',status='validating',data=json.dumps({'analysis':{'topic':'Fixture'},'plan':plan_fixture(),'sources':SOURCES,'assets':[{'path':'fixture','credit':'fixture'}]*3}));db.add(row);db.commit()
    monkeypatch.setattr(service,'check_plan',lambda *a,**k:None)
    monkeypatch.setattr(service,'generate_narration',lambda *a,**k: (_ for _ in ()).throw(service.NarrationUnavailable('Install a compatible Urdu system narrator.')))
    monkeypatch.setattr(service,'render_video',lambda *a,**k:pytest.fail('Must never render missing narration'))
    service.work('speech-fail-fixture','render')
    with SessionLocal() as db:
        row=db.get(TitleShortDraft,'speech-fail-fixture');assert row.status=='failed';assert 'Urdu' in row.error_message;assert not json.loads(row.data).get('video')


@pytest.mark.parametrize('angle',['A complete history of artificial intelligence','A 45-minute educational overview','Tracing major milestones and breakthroughs','A timeline of AI evolution'])
def test_broad_long_video_angles_are_rejected(angle):
    with pytest.raises(ValueError,match='focused short angle'):service.validate_angle({'angle':angle})


def test_one_specific_angle_is_accepted():
    assert service.validate_angle({'angle':'Why did the Dartmouth proposal introduce a new name for this field?'})


def test_missing_optional_search_key_is_clear(monkeypatch):
    monkeypatch.setattr(settings,'title_short_search_provider','brave');monkeypatch.setattr(settings,'brave_search_api_key','')
    with pytest.raises(ValueError,match='Search failed'):service.research({'search_queries':['AI origins']})



def test_broad_analysis_is_repaired_before_any_research(publishable,monkeypatch):
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(role='OWNER').first();row=TitleShortDraft(id='angle-repair-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='The Complete History of Artificial Intelligence',duration=45,language='English',style='educational',status='analyzing',data='{}');db.add(row);db.commit()
    calls=[]
    def ai(prompt,schema):
        if schema==service.Analysis:
            calls.append(prompt)
            return {'topic':'AI','viewer_intent':'Learn an origin story','angle':'A 45-minute educational overview' if len(calls)==1 else 'Why was a new term proposed at one research meeting?', 'rationale':'One question fits a short','search_queries':['original AI proposal']}
        if schema==service.Plan:return plan_fixture()
        return {'supported':True,'reason':'Fixture evidence audit.'}
    monkeypatch.setattr(service,'ai',ai)
    def research(analysis,*unused):
        assert 'overview' not in analysis['angle'];return copy.deepcopy(SOURCES)
    monkeypatch.setattr(service,'research',research)
    service.work('angle-repair-fixture')
    with SessionLocal() as db:
        row=db.get(TitleShortDraft,'angle-repair-fixture');assert row.status=='script_review';assert len(calls)==2


def test_successful_individual_scene_regeneration_preserves_other_scenes(publishable,monkeypatch):
    plan=service.check_plan(draft_fixture(),plan_fixture(),SOURCES,verify=False)
    original_assets=[{'path':'first','hash':'one'},{'path':'second','hash':'two'},{'path':'third','hash':'three'}]
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(role='OWNER').first();row=TitleShortDraft(id='scene-success-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='One focused proposal',duration=45,language='English',style='educational',status='visuals',data=json.dumps({'analysis':{},'sources':SOURCES,'plan':plan,'assets':original_assets,'renders':[{'revision':1,'path':'preserved.mp4','duration':44}]}));db.add(row);db.commit()
    proposal={k:v for k,v in plan['scenes'][1].items() if k not in {'number','start','end'}};proposal['image_query']='A better specific photograph'
    monkeypatch.setattr(service,'ai',lambda *a:proposal)
    monkeypatch.setattr(service,'collect_one',lambda *a:{'path':'new-second','hash':'new-two'})
    service.work('scene-success-fixture','scene',2)
    with SessionLocal() as db:
        row=db.get(TitleShortDraft,'scene-success-fixture');data=json.loads(row.data);assert row.status=='script_review'
        assert data['assets'][0]==original_assets[0] and data['assets'][2]==original_assets[2]
        assert data['assets'][1]['path']=='new-second' and data['renders'][0]['path']=='preserved.mp4'
        assert [s['narration'] for s in data['plan']['scenes']]==[s['narration'] for s in plan['scenes']]



def test_rewrite_changes_only_the_requested_scene_and_returns_to_review(publishable,monkeypatch):
    original=service.check_plan(draft_fixture(),plan_fixture(),SOURCES,verify=False)
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(role='OWNER').first();row=TitleShortDraft(id='scene-rewrite-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='One research question',duration=45,language='English',style='educational',status='script',data=json.dumps({'analysis':{'angle':'One original proposal'},'plan':original,'sources':SOURCES,'assets':[{'path':'first'},{'path':'second'},{'path':'third'}]}));db.add(row);db.commit()
    changed=plan_fixture();changed['scenes'][1]['narration']='The proposal described a research project. Its authors asked how machines could use language and solve problems, giving the research a focused direction.'
    monkeypatch.setattr(service,'ai',lambda prompt,schema:copy.deepcopy(changed) if schema==service.Plan else {'supported':True,'reason':'Fixture source-backed paraphrase.'})
    service.work('scene-rewrite-fixture','rewrite',2,'Make the explanation clearer')
    with SessionLocal() as db:
        row=db.get(TitleShortDraft,'scene-rewrite-fixture');data=json.loads(row.data);assert row.status=='script_review',row.error_message
        assert data['plan']['scenes'][1]['narration']==changed['scenes'][1]['narration']
        assert data['plan']['scenes'][0]['narration']==original['scenes'][0]['narration']
        assert data['assets'][0]['path']=='first' and data['assets'][1] is None and data['assets'][2]['path']=='third'



def test_user_urls_are_not_a_verification_bypass(monkeypatch):
    with pytest.raises(ValueError):service.TitleInput(title='One focused topic',source_urls=['http://127.0.0.1/secret'])
    with pytest.raises(ValueError):service.TitleInput(title='One focused topic',source_urls=['https://random-untrusted.example/facts'])
    monkeypatch.setattr(retrieval,'public_get',lambda *a,**k:(b'<html><p>Too short.</p></html>',{'content-type':'text/html'}))
    with pytest.raises(ValueError,match='Evidence insufficient'):service.research({'search_queries':[]},['https://alpha.edu/article','https://beta.gov/article'])


def test_supplied_sources_retain_fetch_hashes_and_same_evidence_rules(monkeypatch):
    page=('<html><title>Primary proposal</title><h1>Original proposal</h1><p>'+('Researchers described the original study and its scope. '*25)+'</p></html>').encode()
    monkeypatch.setattr(retrieval,'public_get',lambda url,**k:(page if 'alpha.edu' in url else ('<html><title>Independent report</title><p>'+('A different investigator documented the founding proposal with independently worded historical commentary. '*25)+'</p></html>').encode(),{'content-type':'text/html'}))
    diagnostic=[];sources=service.research({'search_queries':[]},['https://alpha.edu/article','https://beta.gov/article'],diagnostic)
    assert len(sources)==2 and all(s['origin']=='user_url' and len(s['retrieved_sha256'])==64 for s in sources)
    assert sources[0]['retrieved_sha256']==hashlib.sha256(page).hexdigest() and sources[1]['retrieved_sha256']!=sources[0]['retrieved_sha256']
    plan=plan_fixture();plan['claims'][0]['source_id']='S999'
    with pytest.raises(ValueError,match='source reference'):service.check_plan(draft_fixture(),plan,sources,verify=False)


def test_missing_urdu_voice_blocks_before_background_generation(publishable,monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','fixture-key')
    monkeypatch.setattr(routes,'preflight',lambda language,*a:{'available':False,'message':'No compatible Urdu narrator; generation has not started.'})
    monkeypatch.setattr(routes,'work',lambda *a:pytest.fail('No job work should begin'))
    response=publishable['client'].post('/api/title-shorts',headers=publishable['owner'],json={'title':'A verified topic','language':'Urdu'})
    assert response.status_code==422 and 'Urdu narrator' in response.json()['detail']
