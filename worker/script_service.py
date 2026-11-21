"""AI Script Generation Service for Phase 2 Local Worker (Gemini + graceful offline fallback)."""

import os
import re
from typing import Optional

_PLACEHOLDER_MARKERS = ("your_gemini_api_key", "your-", "changeme")


def is_valid_gemini_key(api_key: Optional[str]) -> bool:
    """Returns True only when a non-placeholder Gemini API key is configured."""
    if not api_key:
        return False
    cleaned = api_key.strip()
    if len(cleaned) < 12:
        return False
    lowered = cleaned.lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _clean_spoken_script(text: str) -> str:
    """Strips markdown formatting or stage cues so narration reads cleanly via TTS."""
    cleaned = re.sub(r"\[[^\]]+\]", " ", text)
    cleaned = re.sub(r"[*_`#>]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def build_fallback_script(title: str, raw_input: str = "", target_duration_sec: int = 50) -> str:
    """Structured 45-55s NBA/celebrity review Short script template when Gemini is unconfigured."""
    topic = (title or raw_input or "this trending NBA story").strip()
    topic = re.sub(r"\s+", " ", topic).rstrip(".!?")

    paragraphs = [
        f"Wait until you hear the real story behind {topic}.",
        "Most fans only caught the quick headline online, but the full context makes it way more interesting.",
        "When cameras caught the reaction up close, you could tell the tension had been building behind the scenes for weeks.",
        "Analysts pointed out that every statement in that moment was calculated, especially with trade rumors and playoff pressure mounting fast.",
        "Longtime teammates even weighed in, noting how rarely players address a situation this openly mid-season.",
        "Looking at the timeline side by side, the body language and post-game quotes tell a completely different story than social media clips suggested.",
        "What do you think happened next? Drop your take in the comments and follow for the next breakdown.",
    ]

    if target_duration_sec <= 25:
        selected = paragraphs[:3]
    elif target_duration_sec <= 38:
        selected = paragraphs[:5]
    else:
        selected = paragraphs
    return " ".join(selected)


def generate_script(
    input_type: str,
    title: str,
    raw_input: str,
    target_duration_sec: int = 50,
    api_key: Optional[str] = None,
    model: str = "gemini-2.5-flash",
) -> str:
    """Generates a 45-55s Short script for title inputs, or preserves user-provided script inputs."""
    normalized_type = (input_type or "title").strip().lower()
    if normalized_type == "script":
        script_body = (raw_input or title or "").strip()
        if not script_body:
            raise ValueError("Script input is empty")
        return script_body

    resolved_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
    if not is_valid_gemini_key(resolved_key):
        return build_fallback_script(title=title, raw_input=raw_input, target_duration_sec=target_duration_sec)

    desired_words = max(40, min(160, round(target_duration_sec * 2.55)))
    prompt = (
        "Write a tight, engaging spoken narration script for a YouTube Short covering an NBA/celebrity story.\n"
        f"Title/Topic: {title.strip()}\n"
        f"Extra Context: {(raw_input or '').strip()}\n"
        f"Target duration: {target_duration_sec} seconds (~{desired_words} spoken words).\n"
        "Rules:\n"
        "- Output plain spoken sentences only.\n"
        "- NO scene labels, NO brackets, NO markdown, NO emojis, NO bullet points.\n"
        "- Start with a crisp 1-sentence hook referencing the main person or moment, then give clear factual commentary."
    )

    try:
        from google import genai
    except ImportError:
        return build_fallback_script(title=title, raw_input=raw_input, target_duration_sec=target_duration_sec)

    client = genai.Client(api_key=resolved_key.strip())
    candidate_models = list(dict.fromkeys([model, "gemini-2.0-flash"]))
    for candidate in candidate_models:
        try:
            response = client.models.generate_content(model=candidate, contents=prompt)
            text = _clean_spoken_script(getattr(response, "text", "") or "")
            if len(text.split()) >= 15:
                return text
        except Exception:
            continue

    return build_fallback_script(title=title, raw_input=raw_input, target_duration_sec=target_duration_sec)
