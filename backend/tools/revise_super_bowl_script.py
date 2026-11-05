import copy,json,re
from pathlib import Path
from app.database.session import SessionLocal
from app.models import TitleShortDraft
from app.services.title_research import group_sources,norm
from app.services.title_shorts import check_plan,ACTIVE
folder=Path('../generated/super-bowl-script');folder.mkdir(exist_ok=True)
lines=["What does Cam Newton's Super Bowl fumble have to do with Jalen Hurts' ranking? July 2025 reports described Newton questioning Hurts' place among the NFL's top quarterbacks.","Ryan Clark defended Hurts on ESPN's Get Up, then referenced Newton's Super Bowl play involving a loose fumble.","Clark's response paired a defense of Hurts with criticism of that specific Super Bowl moment."]
with SessionLocal() as db:
 d=db.get(TitleShortDraft,'83aed818-f7ff-489f-80fc-4573f844d628')
 if d.revision!=11 or d.status in ACTIVE:raise RuntimeError('Draft changed; refusing to overwrite revisions')
 data=json.loads(d.data);original=copy.deepcopy(data)
 (folder/'before-data.json').write_text(json.dumps({'id':d.id,'revision':d.revision,'status':d.status,'data':original},ensure_ascii=False,indent=2),encoding='utf8')
 sources={s['id']:s for s in data['sources']}
 def passage(sid,pid):
  text=sources[sid]['excerpt'];words=list(re.finditer(r'\S+',text));start=(pid-1)*100;end=min(start+100,len(words))-1
  return {'source_id':sid,'passage_id':pid,'excerpt':text[words[start].start():words[end].end()]}
 evidence=[passage('S1',3),passage('S1',4),passage('S2',2)]
 assert 'fumble' in evidence[1]['excerpt'].lower() and 'fumble' in evidence[2]['excerpt'].lower()
 assert 'Super Bowl' in evidence[1]['excerpt'] and 'Super Bowl' in evidence[2]['excerpt']
 qualifying=[copy.deepcopy(sources['S1']),copy.deepcopy(sources['S2'])]
 assert group_sources(qualifying)==2
 claim={'claim':"Ryan Clark defended Jalen Hurts on ESPN's Get Up and referenced Newton's Super Bowl play involving a loose fumble.",'evidence':evidence}
 data.setdefault('script_history',[]).append({'revision':d.revision,'plan':copy.deepcopy(data['plan']),'scope':copy.deepcopy(data.get('scope'))})
 data.setdefault('evidence_history',[]).append({'revision':d.revision,'evidence_review':copy.deepcopy(data['evidence_review']),'scope':copy.deepcopy(data['scope'])})
 claims=[copy.deepcopy(data['scope']['claims'][0]),claim]
 data['scope']['claims']=claims;data['scope']['focus']="Ryan Clark's defense of Jalen Hurts and his reference to Newton's Super Bowl fumble play."
 for k in ['accepted_fingerprint','accepted_by','accepted_at']:data['scope'].pop(k,None)
 data['evidence_review']['verified_claims']=copy.deepcopy(claims)
 summaries=['Hurts ranking debate','Clark references the Super Bowl','A defense and a Super Bowl criticism']
 for i,s in enumerate(data['plan']['scenes']):s['narration']=lines[i];s['on_screen_text']=summaries[i]
 data['plan']['claims']=[{'claim':c['claim'],'source_id':e['source_id'],'supporting_excerpt':e['excerpt'][:600]} for c in claims for e in c['evidence']]
 data['assets']=[None]*len(lines);data.pop('video',None)
 assert data['sources']==original['sources']
 d.data=json.dumps(data,ensure_ascii=False);check_plan(d,data['plan'],data['sources'],verify=False)
 previous=d.revision
 changed=db.query(TitleShortDraft).filter(TitleShortDraft.id==d.id,TitleShortDraft.revision==previous).update({'revision':previous+1,'data':json.dumps(data,ensure_ascii=False),'status':'script_review','error_message':None},synchronize_session=False)
 if changed!=1:db.rollback();raise RuntimeError('Concurrent edit; no changes applied')
 db.commit()
 (folder/'evidence-map.json').write_text(json.dumps({'revision':previous+1,'claims':claims,'sources':[{'id':s['id'],'url':s['url'],'publisher_group':s['publisher_group'],'independence_group':s.get('independence_group')} for s in data['sources']],'narrations':lines},ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'revision':previous+1,'script':' '.join(lines),'words':len(' '.join(lines).split()),'prior_revision_preserved':True,'independent_groups':2},ensure_ascii=False))
