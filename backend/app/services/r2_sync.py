"""Shared video metadata, fast fingerprinting, and filename-tag helpers for backend & sync scripts."""

import hashlib
import json
from pathlib import Path
import re
import subprocess

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def compute_fast_hash(file_path: Path, sample_bytes: int = 1024 * 1024) -> str:
    """Fast, collision-resistant fingerprint for large video files (start + mid + end + size)."""
    size = file_path.stat().st_size
    hasher = hashlib.sha256()
    hasher.update(str(size).encode("utf-8"))

    with file_path.open("rb") as f:
        if size <= sample_bytes * 3:
            hasher.update(f.read())
        else:
            hasher.update(f.read(sample_bytes))
            f.seek(size // 2)
            hasher.update(f.read(sample_bytes))
            f.seek(max(0, size - sample_bytes))
            hasher.update(f.read(sample_bytes))
    return hasher.hexdigest()


def probe_video_metadata(file_path: Path) -> tuple[float, int, int, str]:
    """Runs ffprobe to extract duration, width, height, and normalized aspect ratio."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration",
        "-of",
        "json",
        str(file_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=True)
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams") or [{}]
        width = int(streams[0].get("width") or 0)
        height = int(streams[0].get("height") or 0)
        duration = round(float((data.get("format") or {}).get("duration") or 0.0), 2)
    except Exception:
        return 0.0, 0, 0, "16:9"

    if width > 0 and height > 0:
        ratio = width / height
        if ratio < 0.8:
            aspect = "9:16"
        elif ratio > 1.2:
            aspect = "16:9"
        else:
            aspect = "1:1"
    else:
        aspect = "16:9"
    return duration, width, height, aspect


def extract_filename_tags(filename: str) -> list[str]:
    """Extracts meaningful lowercase tags from a clip filename while filtering filler words."""
    stem = Path(filename).stem.lower()
    tokens = re.findall(r"[a-z]{3,}", stem)
    stopwords = {"clip", "video", "short", "final", "edit", "mp4", "mov", "the", "and"}
    return sorted({t for t in tokens if t not in stopwords})[:10]
