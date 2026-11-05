"""Opt-in limited evidence drafts. Ranking is not a truth probability."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote
from app.core.network import public_get
from app.research.live import assess, candidate_age_hours
from app.research.verification import verify_story, classify_risk, source_metadata
from app.research.claims import claim_match

LABEL = 'Limited verification — manual review required.'
SCORE_NOTE = 'Ranking score, not probability of truth: freshness 30%, personality relevance 30%, source reliability 25%, headline appeal 15%.'


def draft_decision(data, personality, history=(), fetch=False):
    decision=verify_story(data,data.get('evidence',[]),max_age_hours=candidate_age_hours(data))
    ranked=assess([data],personality.name,json.loads(personality.research_keywords or personality.keywords or '[]'),history,
                  max_age_hours=candidate_age_hours(data))[0]
    reason=None
    if decision['passed']:reason='Fully verified stories use Generate Short.'
    elif decision['risk_level']=='HIGH' or any(classify_risk(s)[0]=='HIGH' for s in data.get('evidence',[])):
        reason='Sensitive claims require full independent verification.'
    elif decision['conflicting_claims']:reason='Unresolved contradictions require source review.'
    elif ranked['status']=='rejected':reason=ranked['rejection_reason']
    elif ranked['overall_score']<.5:reason='Ranking score is below 50/100.'
    # The theme vocabulary must appear, not merely an incidental personality alias.
    theme=[w.casefold() for w in re.findall(r'\w+',personality.category or '') if len(w)>3]
    text=(data['title']+' '+data.get('summary','')).casefold()
    if not reason and theme and not any(w in text for w in theme):reason='Selected theme is not directly supported.'
    supported=[]
    checked=0
    if not reason:
        for row in data.get('evidence',[]):
            if source_metadata(row)['reliability']<.7 or claim_match(data,row)!='supports':continue
            if fetch:
                if checked>=3:break
                checked+=1
                try:
                    body,headers=public_get(row['source_url'],max_bytes=2*1024*1024)
                    raw=body.decode('utf-8',errors='replace')
                    heading=re.search(r'<h1\b[^>]*>(.*?)</h1>',raw,re.I|re.S)
                    content=re.sub(r'</(?:h[1-6]|p|div|li|section)>','. ',raw,flags=re.I)
                    content=re.sub(r'<[^>]+>',' ',content)
                    content=re.sub(r'\s+',' ',content)
                    if re.search(r'access denied|subscribe to continue|captcha|enable javascript',content,re.I):continue
                    # Match the actual accessible article, not an RSS headline or publisher homepage.
                    article={**row,'title':re.sub(r'<[^>]+>',' ',heading[1]) if heading else '', 'summary':content[:30000]}
                    match=claim_match(data,article)
                    if match=='conflict':
                        reason='Accessible source contradicts the core facts; manual source review is required.'
                        break
                    if match!='supports':continue
                except Exception:continue
                row={**row,'access_checked_at':datetime.now(timezone.utc).isoformat()}
            supported.append(row)
        if not supported and not reason:reason='No accessible, identifiable source supports the main claim.'
    return {'eligible':reason is None,'label':LABEL,'reason':reason,'score':round(ranked['overall_score']*100,1),
            'score_explanation':SCORE_NOTE,'missing_corroboration':decision['reason'],
            'sources':supported,'verification':{**decision,'passed':False,'label':LABEL}}


def evergreen_offer(personality):
    """Separately sourced biography suggestion; never manufactures a current event or calls AI."""
    url='https://en.wikipedia.org/api/rest_v1/page/summary/'+quote(personality.name.replace(' ','_'),safe='')
    body,_=public_get(url,hosts=['en.wikipedia.org'])
    data=json.loads(body)
    if data.get('type')=='disambiguation' or not data.get('extract'):raise ValueError('No unambiguous sourced biography found. Choose another personality or supply a primary biography source.')
    if personality.name.casefold() not in data['extract'].casefold():raise ValueError('Biography does not identify the selected personality.')
    return {'title':personality.name+': career background (evergreen)', 'summary':data['extract'],
            'source_url':data['content_urls']['desktop']['page'],'source_name':'Wikipedia biography',
            'retrieved_at':datetime.now(timezone.utc).isoformat(),'verification_status':'source_review_required',
            'note':'Evergreen source suggestion, not current news. Review the biography and its original references before generating; no script has been generated.'}
