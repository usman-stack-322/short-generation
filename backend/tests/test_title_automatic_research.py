import copy,json
from types import SimpleNamespace
import pytest
from app.services import title_research as r,title_evidence as e,title_shorts as s
from app.api import title_shorts as routes
from app.core.config import settings
from app.database.session import SessionLocal
from app.models import TitleShortDraft

TITLE='Ryan Clark & Gillie GO OFF On Cam Newton For Dissing Jalen Hurts: “YOU NEVER WON!”'
def test_neutral_people_and_quote_not_fact():
 lead=r.lead_from_title(TITLE)
 assert lead['people']==['Ryan Clark','Gillie','Cam Newton','Jalen Hurts']
 assert lead['unverified_quotes']==['YOU NEVER WON!']
 qs=r.neutral_queries({'search_queries':[]},lead)
 assert all('GO OFF' not in q and 'YOU NEVER' not in q for q in qs)
 assert any('Gillie' in q and 'Cam Newton' in q for q in qs)

def test_ddg_unwrap_and_entity_filter():
 p=r.Links();p.feed('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.edu%2Fread">Ryan Clark and Cam Newton</a>')
 assert r.unwrap(p.results[0]['url'])=='https://example.edu/read'
 assert r.relevant(p.results[0]['title'],['Ryan Clark','Cam Newton','Jalen Hurts'])
 assert not r.relevant('WhatsApp webcam', ['Ryan Clark','Cam Newton'])

def test_same_wire_and_near_duplicate_are_not_independent():
 a={'url':'https://one.edu/a','publisher_group':'wire','excerpt':'original words '*100}
 b={'url':'https://two.edu/a','publisher_group':'wire','excerpt':'different words '*100}
 assert r.group_sources([a,b])==1
 b['publisher_group']='other';b['excerpt']=a['excerpt']
 assert r.group_sources([a,b])==1

def test_challenge_not_bypassed_and_search_failure_distinct(monkeypatch):
 monkeypatch.setattr(r,'public_get',lambda *a,**k:(b'<div class="anomaly-modal">captcha</div>',{}))
 with pytest.raises(r.ResearchFailure) as err:r.collect({'search_queries':['neutral']},[],[],lambda u:True,{'people':[]})
 assert err.value.code=='search_failed'

def test_metadata_is_not_transcript(monkeypatch):
 monkeypatch.setattr(r,'public_get',lambda *a,**k:(b'{"title":"YOU NEVER WON!","author_name":"Compilation"}',{}))
 m=r.media_metadata('https://www.youtube.com/watch?v=abcdefghijk')
 assert not m['evidence_eligible'] and not m['excerpt'] and 'unavailable' in m['transcript_status']

def test_no_publisher_transcript_is_explicit():
 with pytest.raises(ValueError,match='no readable trusted publisher transcript'):
  r.read_podcast('https://example.edu/feed',b'<rss><channel><item><title>Podcast</title></item></channel></rss>',lambda u:True)

def test_unverified_quote_cannot_enter_plan():
 from test_title_shorts import plan_fixture,SOURCES,draft_fixture
 draft=draft_fixture();draft.data=json.dumps({'evidence_review':{'quote_checks':[{'quote':'YOU NEVER WON!','verified':False}]}})
 plan=plan_fixture();plan['scenes'][0]['on_screen_text']='YOU NEVER WON!'
 with pytest.raises(ValueError,match='Unverified title quote'):s.check_plan(draft,plan,SOURCES,verify=False)

def test_create_idempotency_is_scoped_and_payload_checked(publishable,monkeypatch):
 monkeypatch.setattr(settings,'gemini_api_key','fixture');monkeypatch.setattr(routes,'preflight',lambda *a:{'available':True})
 calls=[];monkeypatch.setattr(routes,'work',lambda *a:calls.append(a))
 payload={'title':TITLE,'request_id':'fixed-request-id','duration':30}
 client=publishable['client'];headers=publishable['owner']
 first=client.post('/api/title-shorts',headers=headers,json=payload)
 second=client.post('/api/title-shorts',headers=headers,json=payload)
 assert first.status_code==second.status_code==201 and first.json()['id']==second.json()['id'] and len(calls)==1
 payload['duration']=45
 assert client.post('/api/title-shorts',headers=headers,json=payload).status_code==409

def test_failed_research_cannot_render_stale_sources(publishable,monkeypatch):
 from test_title_shorts import plan_fixture,SOURCES
 monkeypatch.setattr(settings,'gemini_api_key','fixture');monkeypatch.setattr(routes,'work',lambda *a:None)
 client=publishable['client'];headers=publishable['owner']
 row=client.post('/api/title-shorts',headers=headers,json={'title':TITLE}).json()
 with SessionLocal() as db:
  draft=db.get(TitleShortDraft,row['id']);draft.status='failed';draft.data=json.dumps({'plan':plan_fixture(),'sources':SOURCES,'assets':[None]*3,'research_state':'failed'});db.commit()
 assert client.post('/api/title-shorts/'+row['id']+'/render',headers=headers,json={'revision':1}).status_code==409
 before=client.get('/api/title-shorts/'+row['id'],headers=headers).json()['script']
 retry=client.post('/api/title-shorts/'+row['id']+'/retry',headers=headers,json={'revision':1})
 assert retry.status_code==202 and retry.json()['script']==before
 assert client.post('/api/title-shorts/'+row['id']+'/retry',headers=headers,json={'revision':1}).status_code==409


def test_shared_original_episode_is_not_independent_confirmation():
 a={'url':'https://one.edu/a','publisher_group':'one','excerpt':'one independent phrasing '*100,'primary_links':['https://youtu.be/abcdefghijk']}
 b={'url':'https://two.edu/a','publisher_group':'two','excerpt':'a separate article text '*100,'primary_links':['https://www.youtube.com/watch?v=abcdefghijk']}
 assert r.group_sources([a,b])==1

def test_invalid_excerpts_and_single_source_claims_do_not_pass_incident():
 sources=[{'id':'S1','url':'https://one.edu/a','publisher_group':'one','excerpt':'Ryan Clark and Cam Newton discuss Jalen Hurts.'},{'id':'S2','url':'https://two.edu/a','publisher_group':'two','excerpt':'An independent text about Ryan Clark and Jalen Hurts.'}]
 data={'analysis':{},'sources':sources,'lead':r.lead_from_title(TITLE)}
 decision={'incident_supported':True,'reason':'Claimed by test-only fake auditor','verified_claims':[{'claim':'Gillie responded to Cam Newton','evidence':[{'source_id':'S1','excerpt':'Invented words that are not present'},{'source_id':'S2','excerpt':'Also not actual source words'}]}],'quote_checks':[],'missing_evidence':[],'excluded_claims':[]}
 with pytest.raises(r.ResearchFailure,match='Claim evidence insufficient'):e.verify_incident(None,data,lambda *a:decision)
 assert not data['evidence_review']['incident_supported'] and not data['evidence_review']['verified_claims']
 assert data['evidence_review']['quote_checks'][0]['verified'] is False


def test_evidence_retry_reuses_sources_preserves_plan_assets_and_history(publishable,monkeypatch):
 from test_title_shorts import plan_fixture,SOURCES
 from app.models import WorkspaceMember
 with SessionLocal() as db:
  member=db.query(WorkspaceMember).filter_by(role='OWNER').first()
  plan=plan_fixture();assets=[{'path':'preserved'}]*3
  data={'analysis':{'topic':'Proposal','angle':'One proposal'},'lead':{'people':[]},'sources':copy.deepcopy(SOURCES),'plan':plan,'assets':assets,'renders':[{'revision':1,'path':'old.mp4','duration':44}],'research_state':'failed'}
  db.add(TitleShortDraft(id='audit-resume-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='One original proposal',duration=45,language='English',style='educational',status='research_verification',data=json.dumps(data)));db.commit()
 monkeypatch.setattr(s,'research',lambda *a:pytest.fail('Successful readable retrieval should not be repeated'))
 monkeypatch.setattr(s,'ai',lambda prompt,schema:{'supported':True,'reason':'Explicit test-only source support.'} if schema==s.Audit else pytest.fail('Analysis/script regeneration would discard edits'))
 s.work('audit-resume-fixture','audit')
 with SessionLocal() as db:
  row=db.get(TitleShortDraft,'audit-resume-fixture');data=json.loads(row.data)
  assert row.status=='script_review' and data['research_state']=='verified'
  assert [x['narration'] for x in data['plan']['scenes']]==[x['narration'] for x in plan['scenes']]
  assert data['assets']==assets and data['renders'][0]['path']=='old.mp4' and data['research_history']


def test_evidence_text_is_reconstructed_only_from_existing_passage_ids():
 sources=[{'id':'S1','url':'https://one.edu/a','publisher_group':'one','excerpt':'Ryan Clark and Cam Newton discussed Jalen Hurts in July 2025.'},{'id':'S2','url':'https://two.edu/a','publisher_group':'two','excerpt':'A separate report confirms Ryan Clark and Cam Newton discussed Jalen Hurts during July 2025.'}]
 data={'analysis':{},'sources':sources,'lead':{'people':['Ryan Clark','Cam Newton','Jalen Hurts'],'unverified_quotes':[]}}
 proposal={'incident_supported':True,'reason':'Two actual passages support the narrow fixture claim.','verified_claims':[{'claim':'Ryan Clark and Cam Newton discussed Jalen Hurts in July 2025.','evidence':[{'source_id':'S1','passage_id':1},{'source_id':'S2','passage_id':1}]}],'quote_checks':[],'missing_evidence':[],'excluded_claims':[]}
 result=e.verify_incident(None,data,lambda *a:copy.deepcopy(proposal))
 assert result['verified_claims'][0]['evidence'][0]['excerpt']==sources[0]['excerpt']
 proposal['verified_claims'][0]['evidence'][1]['passage_id']=999
 with pytest.raises(r.ResearchFailure):e.verify_incident(None,data,lambda *a:copy.deepcopy(proposal))
