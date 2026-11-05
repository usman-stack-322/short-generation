"""Shared provider resolution and explicitly non-news development candidates."""
import json
from dataclasses import asdict
from app.services.preferences import preferences
from app.research.engine import DemoResearchProvider,validate_candidate,normalized
from app.core.security import new_id
from app.models import ResearchCandidate,Topic


def configured_provider(db,workspace_id):
    return preferences(db,workspace_id)['research_provider']


def demo_candidates(db,personality,channel_id):
    history={normalized(t.title) for t in db.query(Topic).filter_by(personality_id=personality.id,channel_id=channel_id)}
    rows=[]
    for candidate in DemoResearchProvider().candidates(personality.name,json.loads(personality.research_keywords or '[]')):
        data={**asdict(candidate),'overall_score':validate_candidate(candidate),'provider':'demo',
              'evidence':[],'status':'demo','summary':'Development educational angle, not verified current news.'}
        status='rejected' if normalized(candidate.title) in history else 'demo'
        record=ResearchCandidate(id=new_id(),personality_id=personality.id,channel_id=channel_id,title=candidate.title,
                                status=status,data=json.dumps(data),rejection_reason='Already generated for this channel/theme' if status=='rejected' else None)
        db.add(record);rows.append(record)
    db.commit()
    return rows


def demo_topic(db,record):
    data=json.loads(record.data)
    if record.status!='demo' or data.get('provider')!='demo':raise ValueError('Not a development candidate')
    topic=Topic(id=new_id(),personality_id=record.personality_id,channel_id=record.channel_id,title=record.title,
                source_name=data['source_name'],summary=data['summary'],verification_status='demo',
                **{key:data[key]for key in ('freshness_score','relevance_score','viral_potential_score','reliability_score','overall_score')})
    db.add(topic);db.flush();return topic
