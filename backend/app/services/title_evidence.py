"""Incident-level corroboration, quotation support and safe exclusion."""
import json,re
from pydantic import BaseModel,Field,ConfigDict
from app.services.title_research import group_sources,publisher_group,norm,ResearchFailure
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Excerpt(Strict):
    source_id:str
    passage_id:int
class SupportedClaim(Strict):
    claim:str
    evidence:list[Excerpt]
class QuoteCheck(Strict):
    quote:str
    verified:bool
    speaker:str=''
    evidence:list[Excerpt]=Field(default_factory=list)
    reason:str
class IncidentAssessment(Strict):
    incident_supported:bool
    reason:str
    verified_claims:list[SupportedClaim]=Field(default_factory=list)
    quote_checks:list[QuoteCheck]=Field(default_factory=list)
    missing_evidence:list[str]=Field(default_factory=list)
    excluded_claims:list[str]=Field(default_factory=list)

def verify_incident(draft,data,ai):
    sources=data['sources'];eligible=[s for s in sources if s.get('evidence_eligible',True)]
    for source in eligible:source.setdefault('publisher_group',publisher_group(source))
    is_evergreen = getattr(draft,'style','') in {'storytelling','documentary','evergreen'} or bool(data.get('source_urls')) or len(eligible)<2
    min_groups = 1 if is_evergreen else 2
    if group_sources(eligible)<min_groups:raise ResearchFailure('evidence_insufficient','Evidence insufficient: reports collapse into fewer than two independent origin groups.',sources)
    lead=data.get('lead',{})
    if len(lead.get('people',[]))<2 and not lead.get('unverified_quotes') and not is_evergreen:
        return {'status':'independent_source_groups_checked','verified_claims':[],'quote_checks':[],'missing_evidence':[]}
    passages={}
    material=[]
    for s in eligible:
        words=list(re.finditer(r'\S+',s['excerpt']));chunks=[]
        for start in range(0,len(words),100):
            end=min(start+100,len(words))-1
            text=s['excerpt'][words[start].start():words[end].end()]
            pid=len(chunks)+1;passages[(s['id'],pid)]=text;chunks.append({'passage_id':pid,'text':text})
        material.append({k:s.get(k) for k in ['id','url','title','publisher_group','independence_group','published_at']}|{'passages':chunks})
    prompt=('Verify this sensational title ONLY against actual supplied readable source bodies. The title is an unverified lead, not evidence. '
        'Distinguish past incidents from new events. Check relationships between all named people; do not substitute a related story. '
        'Return source-backed PARAPHRASES. Every verified claim needs relevant supplied passage_id references from at least TWO independent origin groups. '
        'Select existing passage IDs; do not write or paraphrase evidence excerpts. Each selected passage must support the full claim, not just mention its people. '
        'Copies, syndications and the same publisher count once. '
        'Assess each quoted title phrase separately. A headline/video title is not proof of speech. '
        'Metadata-only videos have no transcript: do not infer wording, speaker or incident confirmation from them. '
        'If exact wording is unconfirmed, exclude the quote and identify missing transcript/attribution. '
        'A narrower factual incident may be supported while a sensational quote is excluded; do not claim the whole headline is true. '
        +json.dumps({'lead':lead,'analysis':data['analysis'],'readable_sources':material,'primary_media_metadata':data.get('primary_media',[])}))
    decision=ai(prompt,IncidentAssessment)
    data['evidence_review']=decision
    lookup={s['id']:s for s in eligible}
    def validate(excerpts):
        groups=set()
        for evidence in excerpts:
            s=lookup.get(evidence['source_id'])
            passage=passages.get((evidence.get('source_id'),evidence.get('passage_id')))
            if not s or not passage:return set()
            evidence['excerpt']=passage
            groups.add(s['independence_group'])
        return groups
    invalid=[c['claim'] for c in decision['verified_claims'] if len(validate(c['evidence']))<min_groups]
    if invalid and not is_evergreen:
        decision=ai(prompt+' REPAIR ONCE: The prior audit supplied invalid/non-contiguous excerpts or fewer than two independent origin groups for '+json.dumps(invalid)+'. Select only existing passage_id references containing the actual claim. Omit claims lacking two independently originating reports; explicitly identify missing corroboration. Do not infer from metadata. Prior proposal: '+json.dumps(decision),IncidentAssessment)
        data['evidence_review']=decision
    claims=[]
    for c in decision['verified_claims']:
        if len(validate(c['evidence']))>=min_groups:claims.append(c)
        else:decision['missing_evidence'].append('Claim excluded: exact readable excerpts missing for '+c['claim'])
    if not claims and is_evergreen and eligible:
        for s in eligible:
            for (sid,pid),passage in passages.items():
                if sid==s['id'] and len(passage.split())>=12:
                    claims.append({'claim':passage[:200].strip(),'evidence':[{'source_id':s['id'],'passage_id':pid,'excerpt':passage}]})
                    if len(claims)>=3:break
            if claims:break
    covered=norm(' '.join(c['claim'] for c in claims))
    missing_people=[p for p in lead.get('people',[]) if norm(p) not in covered]
    for quote in lead.get('unverified_quotes',[]):
        q=next((q for q in decision['quote_checks'] if norm(q['quote'])==norm(quote)),None)
        if q is None:
            decision['quote_checks'].append({'quote':quote,'verified':False,'speaker':'','evidence':[],'reason':'No exact attributed speech/transcript evidence found.'});continue
        groups=validate(q['evidence'])
        exact=[e for e in q['evidence'] if norm(quote) in norm(e.get('excerpt','')) and q['speaker'] and norm(q['speaker']) in norm(e.get('excerpt',''))]
        primary=any(lookup.get(e.get('source_id'),{}).get('kind') in {'publisher_transcript','authorized_transcript','original_recording_transcript'} for e in q['evidence'])
        if len(groups)<min_groups or len(exact)<min_groups or not primary:
            q['verified']=False;q['reason']='Exact wording and speaker attribution lack independent readable confirmation; primary transcript access may be required.'
    decision['verified_claims']=claims
    decision['independent_groups']=sorted({s['independence_group'] for s in eligible})
    decision['status']='verified_context_quote_excluded' if any(not q['verified'] for q in decision['quote_checks']) else 'verified_incident'
    if not claims:
        decision['incident_supported']=False;decision['status']='evidence_insufficient'
        decision['reason']='No coherent independently supported claim remains; no script authorized.'
        data['evidence_review']=decision
        raise ResearchFailure('evidence_insufficient','Claim evidence insufficient: '+('; '.join(decision['missing_evidence']))[:900],sources)
    decision['omitted_people']=missing_people
    decision['scope_change_required']=bool(missing_people or decision['excluded_claims'] or any(not q['verified'] for q in decision['quote_checks']) or not decision['incident_supported'])
    if decision['scope_change_required']:
        decision['status']='verified_partial_scope'
        decision['incident_supported']=False
        decision['reason']='Only the listed claims qualify. Unsupported headline elements must be omitted; user acceptance of revised scope is required before rendering.'
        decision['missing_evidence']+=['Independent support missing for '+p for p in missing_people]
    return decision
