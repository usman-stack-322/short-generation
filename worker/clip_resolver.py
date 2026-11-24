"""Celebrity Clip Resolver: picks vault clips via clip_matcher, resolves local:// or R2, and updates usage_count."""

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Optional

import httpx

from backend.app.services.clip_matcher import (
    CelebrityProfile,
    ClipCandidate,
    detect_celebrities,
    plan_clip_timeline,
)
from backend.app.services.r2_sync import probe_video_metadata
from worker.web_fetcher import fetch_original_clips_for_celebrity


@dataclass
class ResolvedCut:
    clip_id: str
    celebrity_id: str
    local_path: Path
    start_sec: float
    cut_duration_sec: float
    match_reason: str
    source_r2_key: str


def resolve_media_path(r2_key: str, cache_dir: Path, storage_mode: str = "local") -> Path:
    """Resolves local:// paths directly from disk, or downloads from R2 in STORAGE_MODE=r2."""
    if r2_key.startswith("local://"):
        local_path = Path(r2_key[len("local://"):])
        if not local_path.is_file():
            raise FileNotFoundError(f"Local clip file not found on disk: {local_path}")
        return local_path

    mode = (storage_mode or "local").strip().lower()
    if mode != "r2":
        raise FileNotFoundError(f"Clip key '{r2_key}' is not a local:// path while STORAGE_MODE={mode}")

    from backend.app.services.r2_storage import R2StorageService

    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_name = r2_key.replace("/", "_")
    dest = cache_dir / safe_name
    if not dest.is_file():
        R2StorageService().client.download_file(
            Bucket=R2StorageService().settings.r2_bucket_name,
            Key=r2_key,
            Filename=str(dest),
        )
    return dest


class ClipResolver:
    """Queries DB catalog via backend API, triggers yt-dlp web fallback when needed, and marks usage."""

    def __init__(
        self,
        api_base_url: str,
        worker_token: str,
        storage_mode: str = "local",
        enable_web_fallback: bool = True,
        web_clips_dir: Path = Path("generated/web_clips"),
        cache_dir: Path = Path("generated/worker_cache"),
        owner_id: Optional[str] = None,
    ):
        self.api_base_url = api_base_url.rstrip("/")
        self.worker_token = worker_token
        self.storage_mode = (storage_mode or "local").strip().lower()
        self.enable_web_fallback = enable_web_fallback
        self.web_clips_dir = web_clips_dir
        self.cache_dir = cache_dir
        self.owner_id = owner_id

    def _worker_headers(self) -> dict[str, str]:
        headers = {"x-worker-token": self.worker_token}
        if self.owner_id:
            headers["x-owner-id"] = self.owner_id
        return headers

    def _fetch_catalog_and_clips(self) -> tuple[list[CelebrityProfile], list[ClipCandidate]]:
        headers = self._worker_headers()
        with httpx.Client(timeout=30) as client:
            celebs_resp = client.get(f"{self.api_base_url}/api/celebrities", headers=headers)
            celebs_resp.raise_for_status()
            clips_resp = client.get(
                f"{self.api_base_url}/api/clips",
                params={"limit": 500},
                headers=headers,
            )
            clips_resp.raise_for_status()

        catalog = [
            CelebrityProfile(
                id=row["id"],
                name=row["name"],
                slug=row["slug"],
                aliases=list(row.get("aliases") or []),
            )
            for row in celebs_resp.json()
        ]
        all_clips = [
            ClipCandidate(
                id=row["id"],
                celebrity_id=row["celebrity_id"],
                r2_key=row["r2_key"],
                duration_sec=float(row.get("duration_sec") or 0.0),
                tags=list(row.get("tags") or []),
                usage_count=int(row.get("usage_count") or 0),
            )
            for row in clips_resp.json()
        ]
        return catalog, all_clips

    def _usable_clips(self, all_clips: list[ClipCandidate]) -> list[ClipCandidate]:
        if self.storage_mode != "local":
            return all_clips
        usable: list[ClipCandidate] = []
        for clip in all_clips:
            if clip.r2_key.startswith("local://"):
                if Path(clip.r2_key[len("local://"):]).is_file():
                    usable.append(clip)
        return usable

    def _extract_candidate_names_from_title(self, title: str) -> list[str]:
        """Extracts Likely Proper Name pairs (e.g. 'LeBron James', 'Ryan Clark') when catalog is empty."""
        matches = re.findall(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})+)\b", title or "")
        stop_words = {"The", "This", "That", "About", "After", "Before", "Shocking", "Final"}
        cleaned: list[str] = []
        for m in matches:
            words = m.split()
            if words[0] in stop_words:
                continue
            if m not in cleaned:
                cleaned.append(m)
        return cleaned[:2]

    def resolve_cuts_for_script(
        self,
        script_text: str,
        target_duration_sec: float,
        cut_length_sec: float = 3.5,
        project_detected_names: Optional[list[str]] = None,
        title: str = "",
    ) -> list[ResolvedCut]:
        catalog, raw_clips = self._fetch_catalog_and_clips()
        usable = self._usable_clips(raw_clips)

        matched = detect_celebrities(f"{title}\n{script_text}", catalog)
        matched_ids = {c.id for c in matched}
        clip_celeb_ids = {c.celebrity_id for c in usable}

        missing_names: list[str] = [c.name for c in matched if c.id not in clip_celeb_ids]
        for name in project_detected_names or []:
            if name not in missing_names and all(c.name.lower() != name.lower() or c.id not in clip_celeb_ids for c in matched):
                missing_names.append(name)

        if not matched and not usable and title:
            missing_names.extend(n for n in self._extract_candidate_names_from_title(title) if n not in missing_names)

        if self.enable_web_fallback and missing_names:
            fetched_items: list[dict] = []
            for celeb_name in missing_names[:2]:
                fetched = fetch_original_clips_for_celebrity(
                    celebrity_name=celeb_name,
                    output_root=self.web_clips_dir,
                    max_clips=2,
                    topic_hint=title,
                    storage_mode=self.storage_mode,
                )
                for item in fetched:
                    local_file = Path(item.pop("local_path"))
                    if self.storage_mode == "r2":
                        from backend.app.services.r2_storage import R2StorageService

                        R2StorageService().upload_file_multipart(local_file, item["r2_key"])
                    fetched_items.append(item)

            if fetched_items:
                with httpx.Client(timeout=30) as client:
                    resp = client.post(
                        f"{self.api_base_url}/api/clips/bulk-index",
                        headers=self._worker_headers(),
                        json={"clips": fetched_items},
                    )
                    resp.raise_for_status()
                catalog, raw_clips = self._fetch_catalog_and_clips()
                usable = self._usable_clips(raw_clips)
                matched = detect_celebrities(f"{title}\n{script_text}", catalog)

        if not usable:
            raise RuntimeError(
                "No usable celebrity video clips found in local vault or web fallback. "
                "Index your clips folder or enable yt-dlp web fallback."
            )

        self._lazy_probe_selected_candidates(
            script_text=f"{title}\n{script_text}",
            matched=matched,
            usable=usable,
            target_duration_sec=target_duration_sec,
            cut_length_sec=cut_length_sec,
        )

        timeline = plan_clip_timeline(
            script_text=f"{title}\n{script_text}",
            target_duration_sec=target_duration_sec,
            matched_celebrities=matched,
            all_clips=usable,
            cut_length_sec=cut_length_sec,
        )
        if not timeline:
            raise RuntimeError("Clip timeline planner returned zero cuts.")

        resolved: list[ResolvedCut] = []
        for cut in timeline:
            resolved.append(
                ResolvedCut(
                    clip_id=cut.clip_id,
                    celebrity_id=cut.celebrity_id,
                    local_path=resolve_media_path(cut.r2_key, cache_dir=self.cache_dir, storage_mode=self.storage_mode),
                    start_sec=cut.start_sec,
                    cut_duration_sec=cut.cut_duration_sec,
                    match_reason=cut.match_reason,
                    source_r2_key=cut.r2_key,
                )
            )
        return resolved

    def _lazy_probe_selected_candidates(
        self,
        script_text: str,
        matched: list[CelebrityProfile],
        usable: list[ClipCandidate],
        target_duration_sec: float,
        cut_length_sec: float,
    ) -> None:
        """Lazily probes only the top shortlisted local:// clips whose duration_sec is 0.0."""
        script_tokens = set(re.findall(r"[a-z0-9]+", script_text.lower()))
        matched_ids = {c.id for c in matched}
        pool = [c for c in usable if c.celebrity_id in matched_ids] or list(usable)
        ranked = sorted(
            pool,
            key=lambda clip: (
                -sum(1 for tag in clip.tags if tag.lower() in script_tokens),
                clip.usage_count,
                clip.id,
            ),
        )
        shortlist_size = max(6, math.ceil(target_duration_sec / max(cut_length_sec, 1.0)) + 2)
        for clip in ranked[:shortlist_size]:
            if clip.duration_sec <= 0 and clip.r2_key.startswith("local://"):
                local_path = Path(clip.r2_key[len("local://"):])
                if local_path.is_file():
                    dur, _, _, _ = probe_video_metadata(local_path)
                    if dur > 0:
                        clip.duration_sec = dur

    def mark_clips_used(self, clip_ids: list[str]) -> int:
        unique_ids = list(dict.fromkeys(cid for cid in clip_ids if cid))
        if not unique_ids:
            return 0
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                f"{self.api_base_url}/api/clips/worker/mark-used",
                headers={"x-worker-token": self.worker_token},
                json={"clip_ids": unique_ids},
            )
            resp.raise_for_status()
            return int(resp.json().get("updated", 0))
