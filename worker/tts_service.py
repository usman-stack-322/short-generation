"""Free AI Voiceover (edge-tts) & High-Contrast ASS Shorts Subtitles Generator."""

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Optional


import os


GOLD_ACTIVE_ASS = "&H000BF5FF"
WHITE_IDLE_ASS = "&H00FFFFFF"


@dataclass
class WordTimestamp:
    text: str
    start_sec: float
    end_sec: float


@dataclass
class NarrationResult:
    audio_path: Path
    ass_path: Path
    duration_sec: float
    word_timestamps: list[WordTimestamp]


def _resolve_heavy_font_name() -> str:
    """Picks a heavy punchy bold display font available on disk for Shorts readability."""
    win_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    search_roots = [
        win_fonts,
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/usr/share/fonts/truetype/dejavu"),
    ]
    candidates = (
        ("ariblk.ttf", "Arial Black"),
        ("impact.ttf", "Impact"),
        ("Montserrat-ExtraBold.ttf", "Montserrat"),
        ("Montserrat-Bold.ttf", "Montserrat"),
        ("arialbd.ttf", "Arial"),
        ("LiberationSans-Bold.ttf", "Liberation Sans"),
        ("DejaVuSans-Bold.ttf", "DejaVu Sans"),
    )
    for filename, family in candidates:
        if any((root / filename).is_file() for root in search_roots):
            return family
    return "Arial Black" if os.name == "nt" else "Arial"


def probe_audio_duration(audio_path: Path) -> float:
    """Returns exact audio duration in seconds via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(audio_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=True)
    data = json.loads(proc.stdout or "{}")
    return round(float((data.get("format") or {}).get("duration") or 0.0), 3)


def estimate_word_timestamps(script_text: str, duration_sec: float) -> list[WordTimestamp]:
    """Proportional fallback word timing when TTS engine omits WordBoundary events."""
    tokens = [t for t in re.split(r"\s+", script_text.strip()) if t]
    if not tokens or duration_sec <= 0:
        return []

    weights = [max(len(re.sub(r"\W+", "", tok)), 2) + (2 if tok[-1] in ".!?" else 0) for tok in tokens]
    total_weight = sum(weights) or len(tokens)

    cursor = 0.0
    words: list[WordTimestamp] = []
    for tok, w in zip(tokens, weights):
        span = duration_sec * (w / total_weight)
        end = min(duration_sec, cursor + max(span, 0.08))
        words.append(WordTimestamp(text=tok, start_sec=round(cursor, 3), end_sec=round(end, 3)))
        cursor = end

    if words:
        words[-1].end_sec = round(duration_sec, 3)
    return words


def group_word_chunks(
    words: list[WordTimestamp],
    min_words: int = 2,
    max_words: int = 3,
) -> list[list[WordTimestamp]]:
    """Groups words into tight, punchy 2-3 word Shorts caption chunks without 1-word orphans."""
    if not words:
        return []
    max_words = max(2, max_words)
    min_words = max(1, min(min_words, max_words))

    groups: list[list[WordTimestamp]] = []
    current: list[WordTimestamp] = []

    for word in words:
        current.append(word)
        ends_sentence = word.text.endswith((".", "!", "?"))
        if len(current) >= max_words or (ends_sentence and len(current) >= min_words):
            groups.append(current)
            current = []

    if current:
        if len(current) == 1 and groups:
            if len(groups[-1]) > min_words:
                groups.append([groups[-1].pop(), current[0]])
            elif len(groups[-1]) < max_words:
                groups[-1].extend(current)
            else:
                groups.append(current)
        else:
            groups.append(current)

    return groups


def chunk_word_timestamps(
    words: list[WordTimestamp],
    min_words: int = 2,
    max_words: int = 3,
) -> list[tuple[float, float, str]]:
    """Groups words into crisp 2-3 word UPPERCASE chunk tuples (start, end, text)."""
    chunks: list[tuple[float, float, str]] = []
    for group in group_word_chunks(words, min_words=min_words, max_words=max_words):
        start = max(0.0, group[0].start_sec)
        end = max(start + 0.15, group[-1].end_sec)
        text = " ".join(w.text for w in group).strip()
        if text:
            chunks.append((round(start, 3), round(end, 3), text))
    return chunks


def _format_ass_time(seconds: float) -> str:
    total_cs = max(0, round(seconds * 100))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}")


def _build_ass_header(play_res: tuple[int, int]) -> str:
    res_x, res_y = play_res
    is_vertical = res_y >= res_x
    font_name = _resolve_heavy_font_name()
    font_size = 82 if is_vertical else 62
    margin_v = 390 if is_vertical else 95
    outline = 5 if is_vertical else 4
    shadow = 3

    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {res_x}",
            f"PlayResY: {res_y}",
            "ScaledBorderAndShadow: yes",
            "WrapStyle: 2",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{font_name},{font_size},&H00FFFFFF,{GOLD_ACTIVE_ASS},&H00000000,&H88000000,"
            f"-1,0,0,0,100,100,1,0,1,{outline},{shadow},2,70,70,{margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )


def write_viral_ass_subtitles(
    word_groups: list[list[WordTimestamp]],
    output_ass: Path,
    play_res: tuple[int, int] = (1080, 1920),
) -> Path:
    """Writes viral Shorts .ass captions with active-word Courtside Gold highlight & pop-in animation."""
    output_ass.parent.mkdir(parents=True, exist_ok=True)
    header = _build_ass_header(play_res)
    events: list[str] = []

    for g_idx, group in enumerate(word_groups):
        if not group:
            continue
        next_chunk_start = word_groups[g_idx + 1][0].start_sec if g_idx + 1 < len(word_groups) else None

        for w_idx, word in enumerate(group):
            ev_start = max(0.0, word.start_sec)
            if w_idx + 1 < len(group):
                ev_end = max(ev_start + 0.04, group[w_idx + 1].start_sec)
            else:
                ev_end = max(ev_start + 0.08, word.end_sec)
                if next_chunk_start is not None:
                    ev_end = min(ev_end, max(ev_start + 0.04, next_chunk_start))

            parts: list[str] = []
            for j, item in enumerate(group):
                token = _escape_ass_text(item.text.upper())
                color_hex = GOLD_ACTIVE_ASS if j == w_idx else WHITE_IDLE_ASS
                parts.append(rf"{{\c{color_hex}&}}{token}")

            anim_prefix = r"{\an2\fscx92\fscy92\t(0,80,\fscx100\fscy100)}" if w_idx == 0 else r"{\an2}"
            text_payload = anim_prefix + " ".join(parts)
            events.append(
                f"Dialogue: 0,{_format_ass_time(ev_start)},{_format_ass_time(ev_end)},Default,,0,0,0,,{text_payload}"
            )

    output_ass.write_text(header + "\n" + "\n".join(events) + "\n", encoding="utf-8")
    return output_ass


def write_ass_subtitles(
    chunks: list[tuple[float, float, str]],
    output_ass: Path,
    play_res: tuple[int, int] = (1080, 1920),
) -> Path:
    """Writes a bold, high-contrast .ass file from (start, end, text) tuples."""
    output_ass.parent.mkdir(parents=True, exist_ok=True)
    header = _build_ass_header(play_res)
    events: list[str] = []
    for start_sec, end_sec, text in chunks:
        display_text = _escape_ass_text(text.upper())
        events.append(
            f"Dialogue: 0,{_format_ass_time(start_sec)},{_format_ass_time(end_sec)},Default,,0,0,0,,"
            rf"{{\an2\fscx92\fscy92\t(0,80,\fscx100\fscy100)}}{display_text}"
        )

    output_ass.write_text(header + "\n" + "\n".join(events) + "\n", encoding="utf-8")
    return output_ass


def create_ass_from_script(
    script_text: str,
    duration_sec: float,
    output_ass: Path,
    word_timestamps: Optional[list[WordTimestamp]] = None,
    max_words_per_chunk: int = 3,
    play_res: tuple[int, int] = (1080, 1920),
) -> Path:
    """Creates bold 2-3 word .ass captions with Courtside Gold active-word highlight."""
    words = word_timestamps if word_timestamps else estimate_word_timestamps(script_text, duration_sec)
    groups = group_word_chunks(words, min_words=max(2, max_words_per_chunk - 1), max_words=max_words_per_chunk)
    return write_viral_ass_subtitles(groups, output_ass=output_ass, play_res=play_res)


async def _synthesize_edge_tts_async(
    script_text: str,
    voice: str,
    audio_path: Path,
) -> list[WordTimestamp]:
    import edge_tts

    try:
        communicate = edge_tts.Communicate(script_text, voice=voice, boundary="WordBoundary")
    except TypeError:
        communicate = edge_tts.Communicate(script_text, voice=voice)

    word_events: list[WordTimestamp] = []
    audio_chunks = bytearray()

    async for message in communicate.stream():
        msg_type = message.get("type")
        if msg_type == "audio" and message.get("data"):
            audio_chunks.extend(message["data"])
        elif msg_type == "WordBoundary":
            raw_text = str(message.get("text") or "").strip()
            if not raw_text:
                continue
            offset_sec = float(message.get("offset") or 0) / 10_000_000.0
            dur_sec = float(message.get("duration") or 0) / 10_000_000.0
            word_events.append(
                WordTimestamp(
                    text=raw_text,
                    start_sec=round(offset_sec, 3),
                    end_sec=round(max(offset_sec + 0.08, offset_sec + dur_sec), 3),
                )
            )

    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(bytes(audio_chunks))
    return word_events


def synthesize_narration(
    script_text: str,
    output_dir: Path,
    voice: str = "en-US-ChristopherNeural",
    max_words_per_chunk: int = 3,
    play_res: tuple[int, int] = (1080, 1920),
) -> NarrationResult:
    """Synthesizes neural TTS MP3 + WordBoundary-aligned Shorts .ass captions."""
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / "narration.mp3"
    ass_path = output_dir / "captions.ass"

    word_events = asyncio.run(_synthesize_edge_tts_async(script_text=script_text, voice=voice, audio_path=audio_path))
    duration_sec = probe_audio_duration(audio_path)
    if duration_sec <= 0 and word_events:
        duration_sec = word_events[-1].end_sec

    words_used = word_events if word_events else estimate_word_timestamps(script_text, duration_sec)
    create_ass_from_script(
        script_text=script_text,
        duration_sec=duration_sec,
        output_ass=ass_path,
        word_timestamps=words_used,
        max_words_per_chunk=max_words_per_chunk,
        play_res=play_res,
    )
    return NarrationResult(
        audio_path=audio_path,
        ass_path=ass_path,
        duration_sec=duration_sec,
        word_timestamps=words_used,
    )
