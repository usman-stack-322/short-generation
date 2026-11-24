#!/usr/bin/env python3
"""Resumable 100 GB Celebrity Vault Bulk Uploader & Auto-Indexer for Cloudflare R2.

Expected local folder structure:
    <root_dir>/
        LeBron James/
            interview_espn.mp4
            press_conference_2025.mp4
        Stephen Curry/
            podcast_clip.mp4

Features:
- Fast partial SHA-256 fingerprinting (reads start + middle + end + file size) so hashing 100 GB takes seconds.
- Local checkpoint file (`sync_checkpoint.json`) so if Wi-Fi drops at 45 GB, re-running skips already-uploaded clips.
- Extracts real video duration, width, height, and aspect ratio using `ffprobe`.
- Supports `--dry-run` to inspect all folders/clips before uploading anything.
"""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.r2_sync import (  # noqa: E402
    VIDEO_EXTENSIONS,
    compute_fast_hash,
    extract_filename_tags,
    probe_video_metadata,
)


@dataclass
class ScannedClip:
    celebrity_name: str
    celebrity_slug: str
    local_path: str
    filename: str
    file_hash: str
    file_size_bytes: int
    duration_sec: float
    width: int
    height: int
    aspect_ratio: str
    r2_key: str
    tags: list[str]


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned or "unknown"


def scan_vault_folder(root_dir: Path, local_only: bool = False) -> list[ScannedClip]:
    """Scans <root_dir>/<Celebrity Name>/* video files."""
    scanned: list[ScannedClip] = []
    if not root_dir.exists() or not root_dir.is_dir():
        raise FileNotFoundError(f"Vault folder not found: {root_dir}")

    for celeb_dir in sorted(p for p in root_dir.iterdir() if p.is_dir()):
        celeb_name = celeb_dir.name.strip()
        celeb_slug = slugify(celeb_name)

        for file_path in sorted(celeb_dir.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue

            file_size = file_path.stat().st_size
            file_hash = compute_fast_hash(file_path)
            duration, width, height, aspect = probe_video_metadata(file_path)
            ext = file_path.suffix.lower()
            r2_key = (
                f"local://{file_path.resolve().as_posix()}"
                if local_only
                else f"vault/celebrities/{celeb_slug}/{file_hash[:16]}{ext}"
            )

            scanned.append(
                ScannedClip(
                    celebrity_name=celeb_name,
                    celebrity_slug=celeb_slug,
                    local_path=str(file_path),
                    filename=file_path.name,
                    file_hash=file_hash,
                    file_size_bytes=file_size,
                    duration_sec=duration,
                    width=width,
                    height=height,
                    aspect_ratio=aspect,
                    r2_key=r2_key,
                    tags=extract_filename_tags(file_path.name),
                )
            )
    return scanned


def _build_index_payload(clip: ScannedClip, category: str) -> dict:
    return {
        "celebrity_name": clip.celebrity_name,
        "category": category,
        "r2_key": clip.r2_key,
        "filename": clip.filename,
        "file_hash": clip.file_hash,
        "file_size_bytes": clip.file_size_bytes,
        "duration_sec": clip.duration_sec,
        "width": clip.width,
        "height": clip.height,
        "aspect_ratio": clip.aspect_ratio,
        "source_type": "vault_upload",
        "tags": clip.tags,
    }


def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_checkpoint(path: Path, uploaded_hashes: set[str]) -> None:
    path.write_text(json.dumps(sorted(uploaded_hashes), indent=2), encoding="utf-8")


def run_sync(
    root_dir: Path,
    api_base_url: Optional[str],
    category: str,
    dry_run: bool,
    checkpoint_path: Path,
    local_only: bool = False,
) -> dict:
    clips = scan_vault_folder(root_dir, local_only=local_only)
    uploaded_hashes = load_checkpoint(checkpoint_path)

    total_gb = sum(c.file_size_bytes for c in clips) / (1024 ** 3)
    pending = [c for c in clips if c.file_hash not in uploaded_hashes]
    unreadable_files = [
        c.local_path for c in clips if c.duration_sec <= 0 and c.width == 0 and c.height == 0
    ]

    summary = {
        "storage_mode": "local" if local_only else "r2",
        "total_clips_found": len(clips),
        "already_synced": len(clips) - len(pending),
        "pending_upload": len(pending),
        "total_size_gb": round(total_gb, 3),
        "celebrities": sorted({c.celebrity_name for c in clips}),
        "unreadable_files": unreadable_files,
        "dry_run": dry_run,
    }

    if dry_run:
        return summary

    import httpx

    if local_only:
        if not api_base_url:
            raise ValueError("api_base_url is required when running --local-only DB indexing")

        endpoint = f"{api_base_url.rstrip('/')}/api/clips/bulk-index"
        inserted_total = 0
        skipped_total = 0
        celebrities_created_total = 0
        batch_size = 50

        for start in range(0, len(pending), batch_size):
            chunk = pending[start : start + batch_size]
            batch_payload = [_build_index_payload(c, category) for c in chunk]
            done_count = min(start + len(chunk), len(pending))
            print(f"[{done_count}/{len(pending)}] Indexing {len(chunk)} local clips into PostgreSQL...")
            resp = httpx.post(endpoint, json={"clips": batch_payload}, timeout=60)
            resp.raise_for_status()
            body = resp.json()
            inserted_total += int(body.get("inserted", 0))
            skipped_total += int(body.get("skipped_existing", 0))
            celebrities_created_total += int(body.get("celebrities_created", 0))
            for clip in chunk:
                uploaded_hashes.add(clip.file_hash)
            save_checkpoint(checkpoint_path, uploaded_hashes)

        summary.update(
            {
                "synced_now": len(pending),
                "inserted_total": inserted_total,
                "skipped_total": skipped_total,
                "celebrities_created_total": celebrities_created_total,
            }
        )
        return summary

    # Import backend R2 service only during Phase 2 R2 uploads
    from backend.app.services.r2_storage import R2StorageService

    storage = R2StorageService()
    batch_payload: list[dict] = []

    for idx, clip in enumerate(pending, start=1):
        print(f"[{idx}/{len(pending)}] Uploading {clip.celebrity_name}/{clip.filename} ({clip.file_size_bytes / 1e6:.1f} MB)...")
        if not storage.object_exists(clip.r2_key):
            storage.upload_file_multipart(Path(clip.local_path), clip.r2_key)

        uploaded_hashes.add(clip.file_hash)
        save_checkpoint(checkpoint_path, uploaded_hashes)

        batch_payload.append(_build_index_payload(clip, category))

        # Flush metadata index to API every 50 clips
        if api_base_url and len(batch_payload) >= 50:
            resp = httpx.post(f"{api_base_url.rstrip('/')}/api/clips/bulk-index", json={"clips": batch_payload}, timeout=60)
            resp.raise_for_status()
            batch_payload.clear()

    if api_base_url and batch_payload:
        resp = httpx.post(f"{api_base_url.rstrip('/')}/api/clips/bulk-index", json={"clips": batch_payload}, timeout=60)
        resp.raise_for_status()

    summary["synced_now"] = len(pending)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumable 100 GB Celebrity Clips Indexer (Local Vault or Cloudflare R2)")
    parser.add_argument("--folder", required=True, help="Path to local Celebrity Clips root folder")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Backend FastAPI base URL for DB indexing")
    parser.add_argument("--category", default="NBA", help="Default category for auto-created celebrities")
    parser.add_argument("--checkpoint", default="sync_checkpoint.json", help="Checkpoint file path for resume support")
    parser.add_argument("--local-only", action="store_true", help="Store local://<full_path> in r2_key and bulk-index into DB without calling R2")
    parser.add_argument("--dry-run", action="store_true", help="Scan and verify metadata without uploading or indexing")
    args = parser.parse_args()

    result = run_sync(
        root_dir=Path(args.folder),
        api_base_url=args.api_url,
        category=args.category,
        dry_run=args.dry_run,
        checkpoint_path=Path(args.checkpoint),
        local_only=args.local_only,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
