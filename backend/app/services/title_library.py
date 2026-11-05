"""Confirmed local media matching. Descriptions guide visuals, never factual evidence."""
import json,re,shutil
from pathlib import Path
from app.database.session import SessionLocal
from app.models import LibraryMedia,MediaCollection,WorkspaceMember,Personality
from app.services.media_library import collection_access,library_path


def copy_local(draft,row):
    from app.services.title_shorts import directory
    source=library_path(row)
    target=directory(draft)/'assets'/('library-'+row.id+source.suffix)
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(source,target)
    return dict(path=str(target),hash=row.content_hash,library_media_id=row.id,kind='local_photo',
        source_url=row.source_url,creator=row.creator,license=row.license,license_url='',
        credit=' | '.join([row.name,row.creator,row.license,row.credit]),
        note='Member-confirmed archival/context image; does not prove the narrated event.')


def match_local(draft,scene,existing):
    data=json.loads(draft.data)
    with SessionLocal() as db:
        member=db.query(WorkspaceMember).filter_by(user_id=draft.creator_id,workspace_id=draft.workspace_id,active=True).first()
        if not member:return None
        collection_access(db,data.get('collection_id'),member)
        rows=db.query(LibraryMedia).filter_by(collection_id=data['collection_id'],approved=True,archived=False,media_type='photo').all()
        used={a.get('hash') for a in existing if a} | set(data.get('excluded_hashes',[]))
        people=[p.casefold() for p in data.get('analysis',{}).get('people',[])]
        text=(scene['visual_description']+' '+scene['image_query']).casefold()
        required=[p for p in people if p in text] or people
        candidates=[]
        for row in rows:
            if row.content_hash in used:continue
            tags=[t.casefold() for t in json.loads(row.tags)]
            person=db.get(Personality,row.personality_id) if row.personality_id else None
            confirmed=tags+([person.name.casefold()] if person else [])
            if required and not all(p in confirmed for p in required):continue
            tokens=set(re.findall(r'\w{3,}',text))
            metadata=set(re.findall(r'\w{3,}',(' '.join(tags)+' '+row.description).casefold()))
            score=len(tokens & metadata)
            if score:candidates.append((score,row))
        if not candidates:return None
        return copy_local(draft,max(candidates,key=lambda pair:pair[0])[1])
