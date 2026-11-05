"""Explicit, content-bound review of narrower researched scopes."""
import hashlib,json,re
from pydantic import BaseModel,ConfigDict
from app.services.title_research import norm
class ScopeProposal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    proposed_title:str
    focus:str

def fingerprint(data):
    plan=data.get('plan')
    if plan:plan={**plan,'scenes':[{k:v for k,v in s.items() if k not in {'number','start','end'}} for s in plan['scenes']]}
    return hashlib.sha256(json.dumps({'scope':{k:v for k,v in data.get('scope',{}).items() if k not in {'accepted_fingerprint','accepted_by','accepted_at'}},'plan':plan,'sources':[(s['id'],s.get('retrieved_sha256'),s.get('publisher_group')) for s in data.get('sources',[])]},sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def accepted(data):
    scope=data.get('scope',{})
    return not scope.get('required') or scope.get('accepted_fingerprint')==fingerprint(data)

def propose(draft,data,ai):
    review=data.get('evidence_review',{})
    if not review.get('scope_change_required'):return None
    claims=review['verified_claims']
    proposal=ai('Propose one accurate neutral title and coherent narrow focus ONLY from the verified claims. Preserve historical dates/context. Do not imply the original headline was confirmed. No spoken quotes, emotional claims or omitted people. '+json.dumps({'original_title':draft.title,'verified_claims':claims,'omitted_people':review.get('omitted_people',[]),'excluded_claims':review.get('excluded_claims',[])}),ScopeProposal)
    title=proposal['proposed_title'].strip();focus=proposal['focus'].strip()
    if not 8<=len(title)<=180 or not 8<=len(focus)<=700:raise ValueError('No coherent revised scope was proposed; review verified claims and retry.')
    omitted=[{'claim':p+' involvement/response','reason':'Insufficient independent originating support','person':p} for p in review.get('omitted_people',[])]
    omitted += [{'claim':q['quote'],'reason':'Exact spoken wording/attribution lacks original recording/transcript and independent support'} for q in review.get('quote_checks',[]) if not q['verified']]
    omitted += [{'claim':c,'reason':'Excluded by the claim-level evidence audit'} for c in review.get('excluded_claims',[])]
    scope={'required':True,'original_title':draft.title,'proposed_title':title,'focus':focus,'claims':claims,'omissions':omitted}
    validate(scope,title+' '+focus)
    return scope

def validate(scope,text):
    if not scope or not scope.get('required'):return
    if re.search(r'[“”"]',text):raise ValueError('Revised scope is paraphrase-only; exact spoken quotations are omitted.')
    for omission in scope.get('omissions',[]):
        if omission.get('person') and norm(omission['person']) in norm(text):raise ValueError('Revised script reintroduced an omitted person: '+omission['person'])
    for omission in scope.get('omissions',[]):
        if len(omission['claim'].split())<8 and not omission.get('person') and norm(omission['claim']) in norm(text):raise ValueError('Revised script reintroduced an omitted title quotation.')
