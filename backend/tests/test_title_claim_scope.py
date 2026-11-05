import copy,json
import pytest
from app.services import title_evidence as e,title_scope as scope,title_shorts as service
from app.services.title_research import ResearchFailure
from app.api import title_shorts as routes
from app.core.config import settings
from app.models import TitleShortDraft
from app.database.session import SessionLocal
from test_title_shorts import plan_fixture,SOURCES


def decision_fixture():
 return {'incident_supported':False,'reason':'Some headline elements have no independent support.','verified_claims':[{'claim':'Ryan Clark and Cam Newton discussed Jalen Hurts in July 2025.','evidence':[{'source_id':'S1','passage_id':1},{'source_id':'S2','passage_id':1}]}],'quote_checks':[{'quote':'YOU NEVER WON!','verified':False,'speaker':'','evidence':[],'reason':'No original recording transcript.'}],'missing_evidence':['Gillie independently originating corroboration missing.'],'excluded_claims':['Gillie responded about a Super Bowl.']}

def sources_fixture():
 return [{'id':'S1','url':'https://one.edu/report','publisher_group':'one','kind':'article','excerpt':'Ryan Clark and Cam Newton discussed Jalen Hurts in July 2025.'},{'id':'S2','url':'https://two.edu/report','publisher_group':'two','kind':'article','excerpt':'A separately written report documents Ryan Clark and Cam Newton discussing Jalen Hurts in July 2025.'}]

def test_supported_claims_survive_unverified_people_and_no_transcript():
 data={'analysis':{},'sources':sources_fixture(),'lead':{'people':['Ryan Clark','Gillie','Cam Newton','Jalen Hurts'],'unverified_quotes':['YOU NEVER WON!']}}
 result=e.verify_incident(None,data,lambda *a:copy.deepcopy(decision_fixture()))
 assert result['status']=='verified_partial_scope' and result['scope_change_required']
 assert result['omitted_people']==['Gillie'] and len(result['verified_claims'])==1
 assert result['verified_claims'][0]['evidence'][0]['excerpt']==data['sources'][0]['excerpt']
 assert not result['quote_checks'][0]['verified']

def test_exact_spoken_quote_needs_original_recording_transcript():
 sources=sources_fixture()
 for s in sources:s['excerpt']+=' Cam Newton said YOU NEVER WON!'
 proposal=decision_fixture();proposal['quote_checks'][0].update(verified=True,speaker='Cam Newton',evidence=[{'source_id':'S1','passage_id':1},{'source_id':'S2','passage_id':1}])
 data={'analysis':{},'sources':sources,'lead':{'people':['Cam Newton'],'unverified_quotes':['YOU NEVER WON!']}}
 result=e.verify_incident(None,data,lambda *a:copy.deepcopy(proposal))
 assert result['quote_checks'][0]['verified'] is False

def test_same_origin_does_not_qualify_partial_scope():
 sources=sources_fixture();sources[1]['publisher_group']='one'
 with pytest.raises(ResearchFailure,match='independent origin groups'):e.verify_incident(None,{'sources':sources},lambda *a:pytest.fail('No AI before origin gate'))

def test_scope_guard_and_fingerprint_bind_edits_not_computed_timing():
 data={'scope':{'required':True,'proposed_title':'A researched debate','omissions':[{'person':'Gillie','claim':'Gillie response'}]},'plan':plan_fixture(),'sources':SOURCES}
 data['scope']['accepted_fingerprint']=scope.fingerprint(data)
 assert scope.accepted(data)
 data['plan']['scenes'][0]['start']=.01
 assert scope.accepted(data)
 data['plan']['scenes'][0]['narration']+=' Edited.'
 assert not scope.accepted(data)
 with pytest.raises(ValueError,match='omitted person'):scope.validate(data['scope'],'Gillie joined the debate')
 with pytest.raises(ValueError,match='paraphrase-only'):scope.validate(data['scope'],'He said "a quotation"')

def test_acceptance_is_explicit_stale_safe_and_revoked_by_script_edit(publishable,monkeypatch):
 client=publishable['client'];headers=publishable['owner'];calls=[]
 monkeypatch.setattr(settings,'gemini_api_key','test-only');monkeypatch.setattr(routes,'preflight',lambda *a:{'available':True});monkeypatch.setattr(routes,'work',lambda *a:calls.append(a))
 row=client.post('/api/title-shorts',headers=headers,json={'title':'Original sensational fixture title','duration':45,'request_id':'scope-fixture-id'}).json();id=row['id']
 data={'analysis':{},'sources':SOURCES,'research_state':'verified','plan':plan_fixture(),'assets':[None]*3,'scope':{'required':True,'proposed_title':'One research proposal','focus':'One original proposal','omissions':[{'person':'Gillie','claim':'Gillie response'}],'claims':[]},'renders':[{'revision':1,'duration':44,'path':'preserved.mp4'}]}
 with SessionLocal() as db:
  draft=db.get(TitleShortDraft,id);draft.status='script_review';draft.data=json.dumps(data);db.commit()
 base='/api/title-shorts/'+id
 assert client.post(base+'/render',headers=headers,json={'revision':1}).status_code==409
 assert client.post(base+'/scope/accept',headers=publishable['editor'],json={'revision':1}).status_code==404
 result=client.post(base+'/scope/accept',headers=headers,json={'revision':1})
 assert result.status_code==200 and result.json()['scope_accepted'] and result.json()['title']=='Original sensational fixture title'
 assert client.post(base+'/scope/accept',headers=headers,json={'revision':1}).status_code==409
 texts=[s['narration'] for s in plan_fixture()['scenes']];texts[0]+=' Read this proposal.'
 result=client.put(base+'/script',headers=headers,json={'revision':2,'narrations':texts})
 assert result.status_code==200 and not result.json()['scope_accepted'] and result.json()['render_history']
 assert client.post(base+'/render',headers=headers,json={'revision':3}).status_code==409
 result=client.post(base+'/scope/accept',headers=headers,json={'revision':3});assert result.status_code==200
 result=client.post(base+'/render',headers=headers,json={'revision':4});assert result.status_code==202 and calls[-1][1]=='render'


def test_narrow_script_audit_does_not_inherit_original_headline_failure(monkeypatch):
 from test_title_shorts import draft_fixture
 draft=draft_fixture();draft.data=json.dumps({'scope':{'required':True,'proposed_title':'One research proposal','focus':'One original proposal','omissions':[{'person':'Gillie','claim':'Gillie response'}]},'evidence_review':{'incident_supported':False,'status':'verified_partial_scope','verified_claims':[{'claim':'A proposal described a research project.'}]}})
 trace=json.loads(draft.data);trace['scope']['claims']=[{'claim':'A proposal described a research project.','evidence':[{'source_id':s['id'],'passage_id':1,'excerpt':s['excerpt']} for s in SOURCES]}];draft.data=json.dumps(trace)
 prompts=[]
 def audit(prompt,schema):
  prompts.append(prompt);return {'supported':True,'reason':'Explicit fixture paraphrase support.'}
 monkeypatch.setattr(service,'ai',audit)
 service.check_plan(draft,plan_fixture(),SOURCES)
 payload=json.loads(prompts[0][prompts[0].index('{"script"'):])
 assert all('passages' in s and 'excerpt' not in s for s in payload['sources'])
 assert payload['allowed_claims'] and 'incident_supported' not in payload and 'original_title' not in payload['scope']
 assert 'separate render gate' in prompts[0] and payload['proposed_title']=='One research proposal'


def test_over_length_candidate_is_repaired_before_script_review(publishable,monkeypatch):
 from app.models import WorkspaceMember
 with SessionLocal() as db:
  member=db.query(WorkspaceMember).filter_by(role='OWNER').first()
  db.add(TitleShortDraft(id='scope-length-repair-fixture',workspace_id=member.workspace_id,creator_id=member.user_id,title='One original research proposal',duration=45,language='English',style='educational',status='research_verification',data=json.dumps({'analysis':{'topic':'Proposal','angle':'One proposal'},'sources':copy.deepcopy(SOURCES),'lead':{'people':[]}})));db.commit()
 calls=[]
 def ai(prompt,schema):
  if schema==service.Plan:
   calls.append(prompt);plan=plan_fixture()
   if len(calls)==1:plan['scenes'][0]['narration']='Excess filler '*250
   return plan
  return {'supported':True,'reason':'Explicit isolated fixture source audit.'}
 monkeypatch.setattr(service,'ai',ai);monkeypatch.setattr(service,'research',lambda *a:pytest.fail('Reuse saved source bodies'))
 service.work('scope-length-repair-fixture','audit')
 with SessionLocal() as db:
  row=db.get(TitleShortDraft,'scope-length-repair-fixture');data=json.loads(row.data)
  assert row.status=='script_review' and len(calls)==2 and 'REPAIR:' in calls[1]
  assert data['rejected_plans'] and 'Excess filler' not in data['plan']['scenes'][0]['narration']
