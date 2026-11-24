"""Config-driven FFmpeg Video Renderer for Phase 2 (9:16 Shorts & 16:9 Long-Form)."""

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
from typing import Optional

from worker.clip_resolver import ResolvedCut
from worker.tts_service import probe_audio_duration


@dataclass(frozen=True)
class RenderProfile:
    name: str
    width: int
    height: int
    fps: int
    cut_length_sec: float
    crf: int
    audio_bitrate: str
    preset: str = "veryfast"


RENDER_PROFILES: dict[str, RenderProfile] = {
    "short": RenderProfile(
        name="short",
        width=1080,
        height=1920,
        fps=30,
        cut_length_sec=3.5,
        crf=20,
        audio_bitrate="160k",
    ),
    "long": RenderProfile(
        name="long",
        width=1920,
        height=1080,
        fps=30,
        cut_length_sec=5.0,
        crf=20,
        audio_bitrate="192k",
    ),
}

XFADE_TRANSITIONS: tuple[str, ...] = ("fade", "smoothleft", "dissolve")
XFADE_DURATION_SEC: float = 0.30


def compute_xfade_schedule(
    cut_durations: list[float],
    transition_sec: float = XFADE_DURATION_SEC,
    total_duration_sec: Optional[float] = None,
) -> tuple[list[float], list[tuple[str, float, float]]]:
    """Calculates per-cut prepared durations and cumulative xfade offsets with zero voiceover drift."""
    clean_durs = [max(0.2, float(d)) for d in cut_durations]
    if not clean_durs:
        raise ValueError("Cannot compute xfade schedule without cuts.")

    cuts_sum = sum(clean_durs)
    target_total = float(total_duration_sec) if total_duration_sec and total_duration_sec > 0 else 0.0

    if len(clean_durs) == 1:
        single_dur = round(target_total, 3) if target_total > 0 else round(clean_durs[0], 3)
        return [single_dur], []

    if target_total > 0:
        if cuts_sum > target_total:
            scale = target_total / cuts_sum
            adjusted_durs = [round(max(0.2, d * scale), 3) for d in clean_durs]
            diff = round(target_total - sum(adjusted_durs), 3)
            if adjusted_durs[-1] + diff >= 0.2:
                adjusted_durs[-1] = round(adjusted_durs[-1] + diff, 3)
        else:
            adjusted_durs = list(clean_durs)
            extra_tail = round(target_total - cuts_sum, 3)
            if extra_tail > 0:
                adjusted_durs[-1] = round(adjusted_durs[-1] + extra_tail, 3)
    else:
        adjusted_durs = list(clean_durs)

    if float(transition_sec) <= 0:
        return [round(d, 3) for d in adjusted_durs], []

    boundary_durations: list[float] = []
    for idx in range(len(adjusted_durs) - 1):
        safe_t = min(float(transition_sec), adjusted_durs[idx] * 0.4, adjusted_durs[idx + 1] * 0.4)
        boundary_durations.append(round(max(0.05, safe_t), 3))

    prep_durations: list[float] = []
    for idx, base_dur in enumerate(adjusted_durs):
        if idx < len(adjusted_durs) - 1:
            prep_durations.append(round(base_dur + boundary_durations[idx], 3))
        else:
            prep_durations.append(round(base_dur, 3))

    transitions: list[tuple[str, float, float]] = []
    current_stream_dur = prep_durations[0]
    for idx, tr_dur in enumerate(boundary_durations):
        offset = round(max(0.0, current_stream_dur - tr_dur), 3)
        tr_name = XFADE_TRANSITIONS[idx % len(XFADE_TRANSITIONS)]
        transitions.append((tr_name, tr_dur, offset))
        current_stream_dur = round(offset + prep_durations[idx + 1], 3)

    return prep_durations, transitions


def get_render_profile(mode: str) -> RenderProfile:
    key = (mode or "short").strip().lower()
    if key not in RENDER_PROFILES:
        raise ValueError(f"Unsupported render mode '{mode}'. Expected one of: {', '.join(RENDER_PROFILES)}")
    return RENDER_PROFILES[key]


def probe_rendered_video(video_path: Path) -> dict:
    """Inspects rendered MP4 streams and container metadata via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=True)
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    v_streams = [s for s in streams if s.get("codec_type") == "video"]
    a_streams = [s for s in streams if s.get("codec_type") == "audio"]
    fmt = data.get("format") or {}
    fmt_duration = round(float(fmt.get("duration") or 0.0), 3)
    v_duration = (
        round(float(v_streams[0].get("duration") or fmt_duration), 3)
        if v_streams
        else 0.0
    )
    a_duration = (
        round(float(a_streams[0].get("duration") or fmt_duration), 3)
        if a_streams
        else 0.0
    )

    return {
        "width": int(v_streams[0].get("width") or 0) if v_streams else 0,
        "height": int(v_streams[0].get("height") or 0) if v_streams else 0,
        "duration_sec": fmt_duration,
        "video_duration_sec": v_duration,
        "audio_duration_sec": a_duration,
        "has_video": bool(v_streams),
        "has_audio": bool(a_streams),
        "video_codec": v_streams[0].get("codec_name") if v_streams else None,
        "audio_codec": a_streams[0].get("codec_name") if a_streams else None,
        "file_size_bytes": video_path.stat().st_size if video_path.is_file() else 0,
    }


def render_video(
    cuts: list[ResolvedCut],
    audio_path: Path,
    output_path: Path,
    ass_path: Optional[Path] = None,
    mode: str = "short",
    target_duration_sec: Optional[float] = None,
    work_dir: Optional[Path] = None,
    transition_duration_sec: float = XFADE_DURATION_SEC,
) -> Path:
    """Scales & center-crops cuts, applies xfade transitions + color polish, burns .ass captions, and normalizes audio."""
    if not cuts:
        raise ValueError("Cannot render video without at least one clip cut.")
    if not audio_path.is_file():
        raise FileNotFoundError(f"Narration audio file not found: {audio_path}")

    profile = get_render_profile(mode)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    active_work_dir = work_dir or (output_path.parent / f".work_{output_path.stem}")
    active_work_dir.mkdir(parents=True, exist_ok=True)

    audio_dur = probe_audio_duration(audio_path)
    total_duration = (
        round(float(target_duration_sec), 3)
        if target_duration_sec and target_duration_sec > 0
        else (audio_dur if audio_dur > 0 else round(sum(c.cut_duration_sec for c in cuts), 3))
    )

    cut_durations = [max(0.2, float(c.cut_duration_sec)) for c in cuts]
    prep_durations, transitions = compute_xfade_schedule(
        cut_durations,
        transition_sec=transition_duration_sec,
        total_duration_sec=total_duration,
    )

    cmd: list[str] = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    graph: list[str] = []

    for idx, (cut, prep_dur) in enumerate(zip(cuts, prep_durations)):
        src = cut.local_path.resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Cut clip file missing on disk: {src}")
        start = max(0.0, float(cut.start_sec))
        cmd.extend(["-ss", f"{start:.3f}", "-t", f"{prep_dur + 0.5:.3f}", "-i", str(src)])
        pad_duration = max(2.0, prep_dur)
        graph.append(
            f"[{idx}:v]"
            f"scale={profile.width}:{profile.height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={profile.width}:{profile.height}:(iw-{profile.width})/2:(ih-{profile.height})/2,"
            f"fps={profile.fps},setsar=1,tpad=stop_mode=clone:stop_duration={pad_duration:.3f},"
            f"trim=duration={prep_dur:.3f},setpts=PTS-STARTPTS,settb=1/{profile.fps},format=yuv420p[v{idx}]"
        )

    audio_idx = len(cuts)
    cmd.extend(["-i", str(audio_path.resolve())])

    if len(cuts) == 1:
        video_stream = "v0"
    elif not transitions:
        concat_inputs = "".join(f"[v{i}]" for i in range(len(cuts)))
        graph.append(f"{concat_inputs}concat=n={len(cuts)}:v=1:a=0,format=yuv420p[vcat]")
        video_stream = "vcat"
    else:
        prev_label = "v0"
        for idx, (tr_name, tr_dur, offset) in enumerate(transitions, start=1):
            next_label = f"xf{idx}"
            graph.append(
                f"[{prev_label}][v{idx}]xfade=transition={tr_name}:duration={tr_dur:.3f}:offset={offset:.3f},"
                f"settb=1/{profile.fps},format=yuv420p[{next_label}]"
            )
            prev_label = next_label
        video_stream = prev_label

    polish_filter = "eq=contrast=1.05:saturation=1.08"
    if ass_path is not None and ass_path.is_file():
        local_ass = active_work_dir / "captions.ass"
        if ass_path.resolve() != local_ass.resolve():
            shutil.copyfile(ass_path, local_ass)
        graph.append(f"[{video_stream}]{polish_filter},ass=captions.ass,format=yuv420p[outv]")
    else:
        graph.append(f"[{video_stream}]{polish_filter},format=yuv420p[outv]")

    graph.append(
        f"[{audio_idx}:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,apad,atrim=duration={total_duration:.3f}[outa]"
    )

    temp_output = active_work_dir / f"{output_path.stem}.rendering.mp4"
    cmd.extend(
        [
            "-filter_complex",
            ";".join(graph),
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-t",
            f"{total_duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            profile.preset,
            "-crf",
            str(profile.crf),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(profile.fps),
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-b:a",
            profile.audio_bitrate,
            "-movflags",
            "+faststart",
            str(temp_output.resolve()),
        ]
    )

    proc = subprocess.run(cmd, cwd=active_work_dir, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-1500:] or f"FFmpeg exited with code {proc.returncode}"
        raise RuntimeError(f"FFmpeg render failed: {detail}")

    if not temp_output.is_file() or temp_output.stat().st_size == 0:
        raise RuntimeError("FFmpeg completed without producing a non-empty MP4 output.")

    temp_output.replace(output_path)
    return output_path
