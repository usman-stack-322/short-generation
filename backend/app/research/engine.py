"""Research candidates, source-independent validation, and duplicate prevention."""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from sqlalchemy.orm import Session
from app.core.security import new_id
from app.models import Personality, Topic

@dataclass
class Candidate:
    title: str
    source_name: str
    source_url: str | None = None
    published_at: datetime | None = None
    freshness_score: float = 0.0
    relevance_score: float = 0.8
    viral_potential_score: float = 0.5
    reliability_score: float = 0.5

class ResearchProvider(Protocol):
    def candidates(self, name: str, keywords: list[str]) -> list[Candidate]: ...

class DemoResearchProvider:
    def candidates(self, name, keywords):
        subject = keywords[0] if keywords else name
        return [Candidate(title, "Local demo research (not live news)") for title in (
            f"Understanding {subject}: a beginner's guide",
            f"How to evaluate headlines about {subject}",
            f"The questions to ask when following {subject}",
        )]

def normalized(title):
    return re.sub(r"\W+", " ", title.casefold()).strip()

def validate_candidate(candidate):
    scores = [candidate.freshness_score, candidate.relevance_score,
              candidate.viral_potential_score, candidate.reliability_score]
    if not candidate.title.strip() or any(not 0 <= s <= 1 for s in scores):
        raise ValueError("Invalid research candidate or scores")
    if candidate.reliability_score < 0.3:
        raise ValueError("Research rejected: source reliability is below the minimum threshold")
    return round(sum(scores) / len(scores), 3)

def research_topic(db: Session, personality: Personality, mode: str, manual_topic: str | None,
                   provider: ResearchProvider | None = None) -> Topic:
    existing = {normalized(row.title) for row in db.query(Topic).filter_by(personality_id=personality.id)}
    if mode == "manual":
        candidates = [Candidate((manual_topic or "").strip(), "User-provided angle (unverified)")]
    else:
        keywords = json.loads(personality.research_keywords or personality.keywords or "[]")
        candidates = (provider or DemoResearchProvider()).candidates(personality.name, keywords)
    ranked = sorted(((validate_candidate(c), c) for c in candidates), key=lambda item: item[0], reverse=True)
    for overall, candidate in ranked:
        if normalized(candidate.title) in existing:
            continue
        topic = Topic(id=new_id(), personality_id=personality.id, overall_score=overall, **vars(candidate))
        db.add(topic)
        db.flush()
        return topic
    raise ValueError("No unique topics remain. Choose a new manual topic.")
