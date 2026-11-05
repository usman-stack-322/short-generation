"""Conservative risk policy and auditable, source-aware corroboration."""
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from functools import lru_cache
from app.core.config import settings, BACKEND_DIR


class SourceMetadata(BaseModel):
    model_config=ConfigDict(extra='forbid')
    hosts: list[str]
    category: Literal['official_primary','major_news','specialist_news','unknown']
    publisher_group: str
    verified_identity: bool = False
    reliability: float = Field(ge=0,le=1)
    primary_paths: list[str] = []
    authoritative_for: list[str] = []


@lru_cache(maxsize=8)
def _registry(path,modified):
    return [SourceMetadata.model_validate(item) for item in json.loads(Path(path).read_text(encoding='utf-8'))['sources']]


def source_metadata(row):
    # Feed-supplied scores/categories cannot promote themselves to trusted authority.
    path=Path(settings.research_sources_file)
    if not path.is_absolute(): path=BACKEND_DIR/path
    records=_registry(str(path.resolve()),path.stat().st_mtime_ns)
    actual=urlsplit(row.get('source_url',''))
    aggregator=(actual.hostname or '').lower()=='news.google.com'
    parsed=urlsplit(row.get('publisher_url','')) if aggregator else actual
    host=(parsed.hostname or '').lower().removeprefix('www.')
    for source in records:
        if host in source.hosts and parsed.scheme=='https' and not parsed.username and source.verified_identity:
            data=source.model_dump()
            data['primary_scope']=not aggregator and any(parsed.path.startswith(prefix) for prefix in source.primary_paths)
            return data
    return {'category':'unknown','publisher_group':host or 'unknown','verified_identity':False,
            'reliability':.35,'authoritative_for':[],'primary_scope':False}


def normalize(text):
    return ' '.join(re.findall(r'\w+',text.casefold()))


def canonical_url(url):
    parsed=urlsplit(url or '')
    query=sorted((k,v) for k,v in parse_qsl(parsed.query) if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid','output','amp'})
    path=re.sub(r'/(?:amp|print)/?$', '',parsed.path).rstrip('/')
    return urlunsplit(('https',(parsed.hostname or '').lower().removeprefix('www.'),path,urlencode(query),''))


def origins(row):
    values=set()
    values.update(normalize(value) for value in row.get('originating_sources',[]) if isinstance(value,str))
    if row.get('originating_source'):values.add(normalize(row['originating_source']))
    text=' '.join(str(row.get(key,'')) for key in ('source_name','author','summary'))
    for wire,pattern in [('reuters',r'\breuters\b'),('associated press',r'\bassociated press\b|\bAP News\b'),('afp',r'\bAFP\b|agence france.presse'),('press association',r'\bpress association\b|\bPA Media\b')]:
        if re.search(pattern,text,re.I):values.add(wire)
    return values


def duplicate_signals(a,b):
    reasons=[]
    left,right=source_metadata(a),source_metadata(b)
    if left['publisher_group']==right['publisher_group']:reasons.append('same publisher group')
    if canonical_url(a.get('canonical_url') or a.get('source_url'))==canonical_url(b.get('canonical_url') or b.get('source_url')):
        reasons.append('same canonical URL')
    if normalize(a['title'])==normalize(b['title']):reasons.append('identical normalized headline')
    if origins(a)&origins(b):reasons.append('same originating wire/source')
    x,y=normalize(a.get('summary','')),normalize(b.get('summary',''))
    if min(len(x.split()),len(y.split()))>=12 and SequenceMatcher(None,x,y).ratio()>=.88:
        reasons.append('highly similar summaries')
    quoted=lambda text:{normalize(q) for q in re.findall(r'["“]([^"”]+)["”]',text) if len(normalize(q).split())>=8}
    if quoted(a.get('summary',''))&quoted(b.get('summary','')):reasons.append('shared extended quotation')
    return reasons


def classify_risk(story):
    text=story['title']+' '+story.get('summary','')
    if re.search(r'\b(crime|criminal|charged|convict\w*|abus\w*|assault\w*|rape|sexual|suicid\w*|diagnos\w*|illness|disease|health condition|mental health|disorder|diabetes|depression|HIV|murder\w*|kill\w*)\b',text,re.I):
        return 'HIGH','sensitive_claim'
    if re.search(r'\b(death|dead|dies|died|injur\w*|arrest\w*|lawsuit|legal|dating|marri\w*|divorc\w*|relationship|personal.life|pregnant|medical|cancer|hospital|scandal|fraud|brib\w*|tax evasion|financial allegation|million|billion|accus\w*|controvers\w*|punish\w*|fined?|walkout)\b',text,re.I):
        return 'HIGH','sensitive_claim'
    if re.search(r'\b(transfer\w*|contract\w*|statement|said|says|coach|performance analysis|tactical|critici\w*|let.{0,50}down)\b',text,re.I):
        return 'MEDIUM','discussion_or_analysis'
    patterns=[('fixture',r'\b(fixtures?|kick.off|match schedule)\b'),
              ('statistics',r'\b(statistics?|milestone|record|goalscoring|scoring charts)\b'),
              ('award',r'\b(award|ballon d.or|golden boot|player of the year|footballer of the year)\b'),
              ('club_announcement',r'\b(club announcement|club announces|official announcement)\b'),
              ('match_result',r'\b(match result|full.time|wins?|won|defeats?|scores?|scored|victory|draw)\b')]
    for kind,pattern in patterns:
        if re.search(pattern,text,re.I):return 'LOW',kind
    return 'MEDIUM','unclassified_claim'


def fresh(row,now,max_age_hours=None):
    try:
        date=datetime.fromisoformat(row['published_at'])
        if date.tzinfo is None:return False
        return -3600 <= (now-date).total_seconds() <= (max_age_hours if max_age_hours is not None else settings.research_max_age_hours)*3600
    except (KeyError,ValueError,TypeError):return False


def verify_story(story,evidence,now=None,max_age_hours=None,historical=False):
    now=now or datetime.now(timezone.utc)
    def in_period(row):
        if not historical:return fresh(row,now,max_age_hours)
        # Historical selection is an explicit server-side policy, never a feed flag.
        # Event dates are required; older publications are allowed, future dates are not.
        try:
            event=datetime.fromisoformat(row['event_date']).replace(tzinfo=timezone.utc)
            published=datetime.fromisoformat(row['published_at']) if row.get('published_at') else None
            return event<=now and bool(row.get('access_checked_at')) and (published is None or published.tzinfo is not None and published<=now)
        except (ValueError,TypeError,KeyError):return False
    # Elevate risk using every corroborating report, not just the mildest headline.
    risks=[classify_risk(item) for item in [story,*evidence]]
    risk,kind=max(risks,key=lambda value:{'LOW':0,'MEDIUM':1,'HIGH':2}[value[0]])
    from app.research.claims import claim_match
    matching=[row for row in evidence if canonical_url(row.get('source_url'))==canonical_url(story.get('source_url')) or claim_match(story,row)=='supports']
    claim_conflict=any(claim_match(story,row)=='conflict' for row in evidence)
    credible=[row for row in matching if source_metadata(row)['reliability']>=.7 and source_metadata(row)['category']!='unknown' and in_period(row)
              and not re.search(r'\b(rumou?r|unconfirmed|speculation|reportedly|allegedly|could join|may join)\b',row['title']+' '+row.get('summary',''),re.I)]
    parents=list(range(len(credible)))
    def find(index):
        while parents[index]!=index:index=parents[index]
        return index
    signals=[]
    for i,a in enumerate(credible):
        for j in range(i):
            reasons=duplicate_signals(a,credible[j])
            if reasons:
                parents[find(i)]=find(j)
                signals.append({'left':i,'right':j,'reasons':reasons})
    independent=len({find(i) for i in range(len(credible))})
    authority=source_metadata(story)
    single=(risk=='LOW' and in_period(story) and authority['verified_identity'] and authority['category']!='unknown' and authority['reliability']>=.9
            and authority['primary_scope'] and kind in authority['authoritative_for']
            and any(canonical_url(row.get('source_url'))==canonical_url(story.get('source_url')) for row in credible))
    numbers=[set(re.findall(r'\b\d+\b',row['title'])) for row in credible]
    conflict=claim_conflict or any(a and b and a!=b for index,a in enumerate(numbers) for b in numbers[:index])
    denials=[bool(re.search(r'\b(no|not|denies|denied|false|hoax|debunk\w*)\b',row['title'],re.I)) for row in credible]
    conflict=conflict or bool(denials and any(denials) and not all(denials))
    story_rumor=bool(re.search(r'\b(rumou?r|unconfirmed|speculation|reportedly|allegedly|could join|may join)\b',story['title']+' '+story.get('summary',''),re.I))
    passed=(independent>=2 or single) and not conflict and in_period(story) and not story_rumor and authority['category']!='unknown'
    label='Single authoritative source' if passed and independent<2 else 'Verified' if passed else 'High-risk hold' if risk=='HIGH' or conflict else 'Needs second source'
    reason=('Conflicting claims require source review.' if conflict else
            'One verified authoritative primary publication covers this low-risk fact.' if passed and independent<2 else
            'At least two independent credible sources corroborate this story.' if passed else
            f'{risk.title()} risk requires stronger corroboration; copied or syndicated reports count once.')
    return {'risk_level':risk,'risk_type':kind,'passed':passed,'label':label,'reason':reason,
            'source_count':len(evidence),'independent_source_count':independent,
            'matched_source_count':len(matching),
            'source_category':authority['category'],'duplicate_signals':signals,'conflicting_claims':conflict}
