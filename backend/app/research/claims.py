"""Conservative local claim matching. Ambiguity is held, never invented away."""
import re

STOP=set('the a an and or of to in on at for with from after before following new update confirmed confirms announced announces said says suffers suffered reaches wins won receives received serious'.split())
GENERIC=set('award ceremony contract match goal goals record milestone performance analysis player club football news story injury transfer statement'.split())

CLAIMS={
    'founding':r'\b(found(?:ed|ing|er)|established|incorporated)\b',
    'launch':r'\b(launched|debut|debuted)\b',
    'acquisition':r'\b(acquired|acquisition|merger|merged)\b',
    'career_change':r'\b(retired|retirement|joined|became|appointed)\b',
    'recovery':r'\b(recovered|recovery|bankruptcy|restructur\w*)\b',
    'death':r'\b(dead|death|dies|died)\b','injury':r'\binjur\w*\b',
    'arrest':r'\barrest\w*\b','legal':r'\b(lawsuit|legal|court)\b',
    'contract':r'\b(contract|extension|renew\w*)\b','transfer':r'\btransfer\w*\b',
    'award':r'\b(award|ballon d.or|golden boot|player of the year|footballer of the year)\b',
    'statistics':r'\b(record|milestone|statistics?)\b',
    'result':r'\b(scores?|scored|scoring|wins?|won|defeat\w*|victory|draw)\b',
    'fixture':r'\b(fixture|kick.off|schedule)\b',
    'analysis':r'\b(analysis|tactical|performance)\b',
}


def signature(row):
    text=row['title']+'. '+row.get('summary','')
    words={w.casefold() for w in re.findall(r'\b[\w-]+\b',text) if len(w)>2}-STOP
    # Explicit relational phrases retain event location/opponent/organization.
    anchors={}
    for key,pattern in {
        'location':r'\b(?:at|in)\s+([A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)',
        'opponent':r'\b(?:against|versus|vs\.?)\s+([A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)',
        'date':r'\b(20\d{2}(?:-\d{2}-\d{2})?)\b',
        'body':r'\b(knee|ankle|hamstring|shoulder|head|back|foot)\b',
        'quantity':r'\b(twice|hat.trick|\d+(?:-\d+)?)\b',
        'award_name':r'\b(Ballon d.Or|Golden Boot|Golden Ball|Player of the Year)\b',
        'competition':r'\b(World Cup|Champions League|Premier League|La Liga|Saudi Pro League)\b',
    }.items():
        values={v.casefold() for v in re.findall(pattern,text)}
        if values:anchors[key]=values
    return words,anchors


def claim_match(story,source):
    left,la=signature(story);right,ra=signature(source)
    text=lambda row:row['title']+'. '+row.get('summary','')
    kinds=lambda row:{key for key,pattern in CLAIMS.items() if re.search(pattern,text(row),re.I)}
    # Prefer the material claim over generic "wins" wording in award stories.
    lk,rk=kinds(story),kinds(source)
    for values in (lk,rk):
        if values-{'result'}:values.discard('result')
    if not lk or lk!=rk:return 'insufficient'
    aliases=story.get('personality_match') or []
    if aliases and not any(alias.casefold() in text(source).casefold() for alias in aliases):return 'insufficient'
    if any(la[key]!=ra[key] for key in la.keys()&ra.keys()):return 'conflict'
    for key in la.keys()-ra.keys():
        if not all(value in text(source).casefold() for value in la[key]):return 'insufficient'
    for key in ra.keys()-la.keys():
        if not all(value in text(story).casefold() for value in ra[key]):return 'insufficient'
    names=lambda row:{w.casefold() for w in re.findall(r'\b[A-Z][a-z]+\b',row['title'])}-STOP-GENERIC
    if not names(story)&names(source):return 'insufficient'
    outcome=lambda row: next((kind for kind,pattern in [
        ('extension',r'\b(extend\w*|extension|renew\w*)\b'),
        ('termination',r'\b(terminat\w*|cancel\w*)\b'),
        ('departure',r'\b(leaves|depart\w*)\b'),
        ('arrival',r'\b(joins|signs|arrival)\b')]
        if re.search(pattern,row['title']+' '+row.get('summary',''),re.I)),None)
    if outcome(story) and outcome(source) and outcome(story)!=outcome(source):return 'conflict'
    shared=left&right
    # Names/boilerplate alone cannot supply a specific claim. Require matching
    # claim categories and a concrete shared anchor; otherwise retain the hold.
    anchor=any(la[key]==ra[key] for key in la.keys()&ra.keys())
    if anchor and len(shared)>=2:return 'supports'
    return 'insufficient'
