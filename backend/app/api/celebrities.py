import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Celebrity, MediaClip, User
from ..schemas import CelebrityCreate, CelebrityOut
from ..services.clip_matcher import slugify
from .deps import get_current_owner

router = APIRouter(prefix="/api/celebrities", tags=["celebrities"])


@router.get("", response_model=list[CelebrityOut])
def list_celebrities(
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
):
    rows = db.execute(
        select(
            Celebrity,
            func.count(MediaClip.id).label("clip_count"),
            func.coalesce(func.sum(MediaClip.duration_sec), 0.0).label("total_duration"),
        )
        .outerjoin(MediaClip, MediaClip.celebrity_id == Celebrity.id)
        .where(Celebrity.owner_id == owner.id)
        .group_by(Celebrity.id)
        .order_by(Celebrity.name.asc())
    ).all()

    return [
        CelebrityOut(
            id=celeb.id,
            name=celeb.name,
            slug=celeb.slug,
            aliases=json.loads(celeb.aliases_json or "[]"),
            category=celeb.category,
            clip_count=int(clip_count),
            total_duration_sec=round(float(total_duration), 2),
            created_at=celeb.created_at,
        )
        for celeb, clip_count, total_duration in rows
    ]


@router.post("", response_model=CelebrityOut, status_code=201)
def create_celebrity(
    payload: CelebrityCreate,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
):
    slug = slugify(payload.name)
    existing = db.execute(
        select(Celebrity).where(Celebrity.owner_id == owner.id, Celebrity.slug == slug)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Celebrity '{payload.name}' already exists")

    celeb = Celebrity(
        owner_id=owner.id,
        name=payload.name.strip(),
        slug=slug,
        aliases_json=json.dumps([a.strip() for a in payload.aliases if a.strip()]),
        category=payload.category.strip() or "NBA",
    )
    db.add(celeb)
    db.commit()
    db.refresh(celeb)

    return CelebrityOut(
        id=celeb.id,
        name=celeb.name,
        slug=celeb.slug,
        aliases=json.loads(celeb.aliases_json),
        category=celeb.category,
        clip_count=0,
        total_duration_sec=0.0,
        created_at=celeb.created_at,
    )
