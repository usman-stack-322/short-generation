import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import Field
from app.core.security import require_editor
from app.database.session import get_db
from app.models import Personality, ResearchCandidate, Channel
from app.schemas import InputModel
from app.youtube.permissions import channel_access
from app.research.live import research_live, similar, candidate_age_hours
from app.research.verification import verify_story
from app.api.access import _accessible_channel_ids,personality_visible

router=APIRouter(prefix='/api/research',tags=['Research'])


class ResearchInput(InputModel):
    channel_id:str
    personality_id:str


def candidate_access(db,record,member):
    if not record:
        raise HTTPException(404,'Research candidate not found')
    channel_access(db.get(Channel,record.channel_id),member,True)


@router.post('/candidates')
def candidates(payload:ResearchInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    channel_access(db.get(Channel,payload.channel_id),context[1],True)
    personality=db.get(Personality,payload.personality_id)
    if not personality_visible(personality,context[1],_accessible_channel_ids(db,context[1])) or personality.channel_id not in {None,payload.channel_id}:
        raise HTTPException(404,'Assigned personality not found')
    try:
        from app.research.selection import configured_provider,demo_candidates
        rows=(research_live(db,personality,payload.channel_id) if configured_provider(db,context[1].workspace_id)=='rss'
              else demo_candidates(db,personality,payload.channel_id))
        # Preserve access to saved source review across picker refreshes. Recheck
        # current policy and history; a provider failure still raises above.
        if configured_provider(db,context[1].workspace_id)=='rss':
            from app.models import Topic
            history=[t.title for t in db.query(Topic).filter_by(channel_id=payload.channel_id,personality_id=personality.id)]
            ids={r.id for r in rows}
            for saved in db.query(ResearchCandidate).filter_by(channel_id=payload.channel_id,personality_id=personality.id,status='verified'):
                data=json.loads(saved.data)
                if saved.id not in ids and verify_story(data,data.get('evidence',[]),max_age_hours=candidate_age_hours(data))['passed'] and not any(similar(saved.title,title) for title in history):
                    rows.append(saved)
        return [{'id':r.id,**json.loads(r.data),'status':r.status,'rejection_reason':r.rejection_reason} for r in rows]
    except ValueError as exc:
        from app.services.preferences import notify
        notify(db,context[1].workspace_id,payload.channel_id,'Research failed',str(exc))
        db.commit()
        raise HTTPException(422,str(exc)) from None


class VerificationInput(InputModel):
    confirmed:bool
    note:str=Field(min_length=20,max_length=1000)


@router.post('/{candidate_id}/verify')
def verify(candidate_id:str,payload:VerificationInput,context=Depends(require_editor),db:Session=Depends(get_db)):
    record=db.get(ResearchCandidate,candidate_id)
    candidate_access(db,record,context[1])
    data=json.loads(record.data)
    evidence=data.get('evidence',[])
    decision=verify_story(data,evidence,max_age_hours=candidate_age_hours(data))
    if record.status=='rejected' or not payload.confirmed or not decision['passed']:
        raise HTTPException(409,decision['reason'])
    data['verification']=decision
    if evidence: evidence[0]['verification']=decision
    data['review']={'member_id':context[1].id,'note':payload.note}
    record.status,record.rejection_reason='verified',None
    record.data=json.dumps(data)
    db.commit()
    return {'id':record.id,'status':'verified'}
