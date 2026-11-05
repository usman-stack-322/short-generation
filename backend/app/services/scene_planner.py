"""Deterministic, complete narration coverage with word-weighted timings."""
import math
from app.core.security import new_id
from app.models import Scene,Personality
from app.core.languages import language_info,text_units


def plan_scenes(script, duration, personality, suggestions=None, language='en-US'):
    words = text_units(script,language)
    separator='' if language_info(language).code=='zh-CN' else ' '
    count = min(12, max(6, round(duration/5)))
    count = min(count, max(1,len(words)))
    rows=[]
    for i in range(count):
        begin, end = round(i*len(words)/count), round((i+1)*len(words)/count)
        text=separator.join(words[begin:end])
        hint = suggestions[i] if suggestions and i < len(suggestions) else {}
        query = hint.get('visual_query') or personality
        rows.append({'scene_number':i+1,'start_time':round(duration*begin/max(1,len(words)),3),
                     'end_time':round(duration*end/max(1,len(words)),3),'narration':text,
                     'visual_query':query[:300],'visual_type':'image','caption':' '.join(text.split()[:6]),
                     'emphasis_word':max(text.split(),key=len,default='')[:80]})
    return rows


def save_scenes(db, job, suggestions=None):
    import json
    db.query(Scene).filter_by(job_id=job.id).delete(synchronize_session=False)
    personality=db.get(Personality,job.personality_id)
    subject=personality.name if personality else 'editorial illustration'
    for data in plan_scenes(job.script.full_script,job.duration-.6,subject,suggestions,job.language_code):
        evidence=json.loads(job.topic.evidence or '[]') if job.topic else []
        if data['scene_number']==1 and evidence and evidence[0].get('content_type')=='historical':
            data['caption']=evidence[0]['event_date'][:4]+' · '+data['caption']
        db.add(Scene(id=new_id(),job_id=job.id,**data))
    db.flush()
