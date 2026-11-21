"""Strict Original Web Footage Fetcher via yt-dlp (NEVER downloads AI-generated video)."""

from pathlib import Path
import re
from typing import Optional

from backend.app.services.clip_matcher import slugify
from scripts.bulk_sync_r2 import (
    compute_fast_hash,
    extract_filename_tags,
    probe_video_metadata,
)

DISALLOWED_PATTERNS = (
    r"\bai[\s_-]?generated\b",
    r"\bai[\s_-]?video\b",
    r"\bai[\s_-]?voice\b",
    r"\bsora\b",
    r"\brunway\b",
    r"\bmidjourney\b",
    r"\bdeepfake\b",
    r"\bnba[\s_-]?2k\b",
    r"\b2k2[0-9]\b",
    r"\bparody\b",
    r"\banimation\b",
    r"\bcartoon\b",
    r"\bcgi\b",
)


def is_allowed_original_video(title: str, description: str = "") -> bool:
    """Rejects synthetic/AI/video-game clips so only authentic real-world footage is accepted."""
    combined = f"{title or ''} {description or ''}".lower().strip()
    if not combined:
        return False
    return not any(re.search(pattern, combined) for pattern in DISALLOWED_PATTERNS)


def fetch_original_clips_for_celebrity(
    celebrity_name: str,
    output_root: Path = Path("generated/web_clips"),
    max_clips: int = 2,
    max_duration_sec: int = 180,
    topic_hint: str = "",
    storage_mode: str = "local",
    category: str = "NBA",
) -> list[dict]:
    """Searches & downloads real interview/NBA clips via yt-dlp when a celebrity is missing from Vault."""
    try:
        import yt_dlp
    except ImportError:
        return []

    celeb_slug = slugify(celebrity_name)
    target_dir = output_root / celeb_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    hint_tokens = re.findall(r"[A-Za-z0-9]{3,}", topic_hint or "")[:3]
    hint_phrase = " ".join(hint_tokens)
    query = f"ytsearch6:{celebrity_name} {hint_phrase} interview press conference".strip()

    search_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "ignoreerrors": True,
    }

    candidates: list[dict] = []
    try:
        with yt_dlp.YoutubeDL(search_opts) as ydl:
            info = ydl.extract_info(query, download=False)
        for entry in (info or {}).get("entries") or []:
            if not entry or entry.get("is_live"):
                continue
            dur = float(entry.get("duration") or 0.0)
            if dur < 5 or dur > max_duration_sec:
                continue
            title = str(entry.get("title") or "")
            desc = str(entry.get("description") or "")
            if not is_allowed_original_video(title, desc):
                continue
            webpage_url = entry.get("webpage_url") or entry.get("original_url")
            if webpage_url:
                candidates.append({"url": webpage_url, "title": title})
            if len(candidates) >= max_clips * 2:
                break
    except Exception:
        return []

    downloaded: list[dict] = []
    download_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(target_dir / "%(id)s.%(ext)s"),
        "retries": 2,
        "socket_timeout": 20,
    }

    for candidate in candidates:
        if len(downloaded) >= max_clips:
            break
        try:
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                result = ydl.extract_info(candidate["url"], download=True)
                raw_file = ydl.prepare_filename(result)
            file_path = Path(raw_file)
            if not file_path.is_file():
                mp4_alt = file_path.with_suffix(".mp4")
                if mp4_alt.is_file():
                    file_path = mp4_alt
                else:
                    continue

            file_hash = compute_fast_hash(file_path)
            duration_sec, width, height, aspect = probe_video_metadata(file_path)
            if duration_sec <= 0 or width <= 0:
                continue

            ext = file_path.suffix.lower() or ".mp4"
            is_local = (storage_mode or "local").strip().lower() == "local"
            r2_key = (
                f"local://{file_path.resolve().as_posix()}"
                if is_local
                else f"vault/web_clips/{celeb_slug}/{file_hash[:16]}{ext}"
            )
            tags = sorted(set(extract_filename_tags(candidate["title"] + " " + file_path.name) + ["interview", "original"]))[:10]

            downloaded.append(
                {
                    "celebrity_name": celebrity_name.strip(),
                    "category": category,
                    "r2_key": r2_key,
                    "local_path": str(file_path.resolve()),
                    "filename": file_path.name,
                    "file_hash": file_hash,
                    "file_size_bytes": file_path.stat().st_size,
                    "duration_sec": duration_sec,
                    "width": width,
                    "height": height,
                    "aspect_ratio": aspect,
                    "source_type": "web_original",
                    "source_url": candidate["url"],
                    "tags": tags,
                }
            )
        except Exception:
            continue

    return downloaded
