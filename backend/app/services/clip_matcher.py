"""Smart Celebrity Detection & Least-Used Clip Selection Engine (Pure Python, 100% Testable).

Priority rules:
1. Detect celebrities mentioned in Title/Script via exact name or alias matching.
2. Prefer clips whose tags match keywords in the script (e.g. 'interview', 'dunk', 'podcast').
3. If no exact topic/tag match exists, seamlessly fall back to least-used clips of that celebrity
   so Shorts generation never crashes or stalls.
4. If even a single clip is shorter than target duration, cycle clips cleanly with varied start offsets.
"""

from dataclasses import dataclass, field
import re
from typing import Iterable


@dataclass
class CelebrityProfile:
    id: str
    name: str
    slug: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class ClipCandidate:
    id: str
    celebrity_id: str
    r2_key: str
    duration_sec: float
    tags: list[str] = field(default_factory=list)
    usage_count: int = 0


@dataclass
class PlannedCut:
    clip_id: str
    celebrity_id: str
    r2_key: str
    start_sec: float
    cut_duration_sec: float
    match_reason: str  # "tag_match" | "celebrity_fallback" | "vault_fallback"


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned or "unknown"


def detect_celebrities(text: str, catalog: Iterable[CelebrityProfile]) -> list[CelebrityProfile]:
    """Detects mentioned celebrities by full name or aliases, ordered by first appearance."""
    lowered = text.lower()
    found: list[tuple[int, CelebrityProfile]] = []

    for celeb in catalog:
        terms = [celeb.name] + list(celeb.aliases)
        earliest_pos: int | None = None
        for term in terms:
            t = term.strip().lower()
            if len(t) < 2:
                continue
            pattern = r"(?<!\w)" + re.escape(t) + r"(?!\w)"
            match = re.search(pattern, lowered)
            if match:
                pos = match.start()
                if earliest_pos is None or pos < earliest_pos:
                    earliest_pos = pos
        if earliest_pos is not None:
            found.append((earliest_pos, celeb))

    found.sort(key=lambda item: item[0])
    return [celeb for _, celeb in found]


def plan_clip_timeline(
    script_text: str,
    target_duration_sec: float,
    matched_celebrities: list[CelebrityProfile],
    all_clips: list[ClipCandidate],
    cut_length_sec: float = 3.5,
) -> list[PlannedCut]:
    """Builds a complete cut timeline covering target_duration_sec with zero gaps."""
    if target_duration_sec <= 0 or not all_clips:
        return []

    script_tokens = set(re.findall(r"[a-z0-9]+", script_text.lower()))
    matched_ids = [c.id for c in matched_celebrities]

    # Filter clips belonging to detected celebrities first
    celeb_clips = [c for c in all_clips if c.celebrity_id in matched_ids]
    using_vault_fallback = False

    if not celeb_clips:
        # Ultimate fallback: if celebrity isn't in Vault yet, use least-used general vault clips
        celeb_clips = list(all_clips)
        using_vault_fallback = True

    def score_clip(clip: ClipCandidate) -> tuple[int, int, str]:
        tag_hits = sum(1 for tag in clip.tags if tag.lower() in script_tokens)
        # Higher tag_hits first (-tag_hits), then lowest usage_count, then deterministic id
        return (-tag_hits, clip.usage_count, clip.id)

    ranked = sorted(celeb_clips, key=score_clip)

    timeline: list[PlannedCut] = []
    covered = 0.0
    idx = 0
    clip_offsets: dict[str, float] = {}

    while covered < target_duration_sec:
        clip = ranked[idx % len(ranked)]
        remaining = target_duration_sec - covered
        safe_clip_dur = max(clip.duration_sec, 1.0)
        desired_cut = min(cut_length_sec, remaining, safe_clip_dur)

        start_sec = clip_offsets.get(clip.id, 0.0)
        if start_sec + desired_cut > safe_clip_dur:
            start_sec = 0.0

        next_offset = start_sec + desired_cut
        clip_offsets[clip.id] = next_offset if next_offset < safe_clip_dur else 0.0

        tag_hits = sum(1 for tag in clip.tags if tag.lower() in script_tokens)
        if using_vault_fallback:
            reason = "vault_fallback"
        elif tag_hits > 0:
            reason = "tag_match"
        else:
            reason = "celebrity_fallback"

        timeline.append(
            PlannedCut(
                clip_id=clip.id,
                celebrity_id=clip.celebrity_id,
                r2_key=clip.r2_key,
                start_sec=round(start_sec, 2),
                cut_duration_sec=round(desired_cut, 2),
                match_reason=reason,
            )
        )
        covered += desired_cut
        idx += 1

    return timeline
