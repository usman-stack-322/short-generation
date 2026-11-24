"""AI Script Generation Service for Phase 2 Local Worker (Gemini)."""

import os
import re
import secrets
from typing import Optional
import uuid

_PLACEHOLDER_MARKERS = ("your_gemini_api_key", "your-", "changeme")

HOOK_STYLES: tuple[str, ...] = (
    "Cold-open reaction: drop straight into the exact viral moment or quote from the title.",
    "Sharp curiosity question tied directly to the main person and stakes in the title.",
    "Contrarian breakdown: challenge the obvious surface take on the exact event in the title.",
    "Timeline twist: spotlight the hidden turning point right before the headline moment.",
    "Stat or career-stakes opener: frame what this specific moment means for the person's legacy or season.",
    "Courtside/mic'd-up scene setter: paint the exact setting and body language of the moment.",
    "Rivalry or matchup spotlight: focus immediately on the tension between the specific figures in the title.",
    "Direct verdict opener: open with a bold one-sentence takeaway about the title's exact event, then back it up.",
)

SYSTEM_INSTRUCTION = (
    "You are an elite NBA and pop-culture YouTube Shorts scriptwriter. "
    "Write a fresh, original spoken narration strictly grounded in the exact person, event, teams, quotes, "
    "and angle named in the user's title and extra context. "
    "Follow these rules strictly:\n"
    "- Adapt structure, tone, and vocabulary uniquely to the provided title; never reuse generic stock templates.\n"
    "- Forbidden boilerplate cliches (never output unless literally quoted in the title): "
    "'Wait until you hear the real story behind', 'Most fans only caught the quick headline', "
    "'cameras caught the reaction', 'trade rumors and playoff pressure'.\n"
    "- Output plain spoken sentences only: NO markdown, NO brackets, NO scene labels, NO emojis, NO bullet points.\n"
    "- End with a short audience question anchored directly to the specific subject in the title."
)


class ScriptGenerationError(RuntimeError):
    """Raised when AI script generation fails so errors surface instead of generic canned text."""


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


def _redact_secret(message: str, secret: str) -> str:
    """Removes the API key from error strings before bubbling errors to logs or UI."""
    cleaned_secret = (secret or "").strip()
    if len(cleaned_secret) >= 4 and cleaned_secret in message:
        return message.replace(cleaned_secret, "[REDACTED]")
    return message


def build_script_prompt(
    title: str,
    raw_input: str = "",
    target_duration_sec: int = 50,
    hook_style: Optional[str] = None,
    generation_nonce: Optional[str] = None,
) -> tuple[str, str]:
    """Constructs a title-grounded prompt with varied hook framing and anti-repetition guardrails."""
    clean_title = re.sub(r"\s+", " ", (title or "").strip())
    clean_raw = re.sub(r"\s+", " ", (raw_input or "").strip())
    chosen_hook = hook_style or secrets.choice(HOOK_STYLES)
    nonce = generation_nonce or uuid.uuid4().hex[:8]
    desired_words = max(40, min(160, round(target_duration_sec * 2.55)))

    context_line = ""
    if clean_raw and clean_raw.lower() != clean_title.lower():
        context_line = f"Extra Context: {clean_raw}\n"

    prompt = (
        f"Request ID: {nonce}\n"
        f"Title/Topic: {clean_title}\n"
        f"{context_line}"
        f"Target duration: {target_duration_sec} seconds (~{desired_words} spoken words).\n"
        f"Required Opening Hook Style: {chosen_hook}\n"
        "Requirements:\n"
        "- Center every sentence specifically on the exact topic, people, and angle in Title/Topic.\n"
        "- Do NOT repeat phrasing, generic intros, or filler lines across different titles.\n"
        "- Open immediately using the Required Opening Hook Style without meta-commentary.\n"
        "- Write crisp, punchy spoken English sentences ready for voiceover.\n"
        "- End with one concise closing question tailored specifically to this Title/Topic."
    )
    return prompt, chosen_hook


def generate_script(
    input_type: str,
    title: str,
    raw_input: str,
    target_duration_sec: int = 50,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.9,
    top_p: float = 0.95,
    hook_style: Optional[str] = None,
) -> str:
    """Generates a unique, title-specific Short script via Gemini, or preserves user-provided script inputs."""
    normalized_type = (input_type or "title").strip().lower()
    if normalized_type == "script":
        script_body = (raw_input or title or "").strip()
        if not script_body:
            raise ValueError("Script input is empty")
        return script_body

    clean_title = (title or raw_input or "").strip()
    if not clean_title:
        raise ValueError("Title is required for title-to-script generation.")

    resolved_key = (api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")).strip()
    if not is_valid_gemini_key(resolved_key):
        raise ScriptGenerationError(
            "GEMINI_API_KEY is missing or still a placeholder. Configure a valid Gemini API key in .env "
            "(or use Paste / .txt Script mode)."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ScriptGenerationError("google-genai is not installed. Run: pip install -r worker/requirements.txt") from exc

    effective_temp = max(0.85, min(0.95, float(temperature)))
    prompt, _ = build_script_prompt(
        title=clean_title,
        raw_input=raw_input,
        target_duration_sec=target_duration_sec,
        hook_style=hook_style,
    )
    config = types.GenerateContentConfig(
        temperature=effective_temp,
        top_p=float(top_p),
        system_instruction=SYSTEM_INSTRUCTION,
    )

    client = genai.Client(api_key=resolved_key)
    primary_model = (model or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    candidate_models = list(dict.fromkeys([primary_model, "gemini-2.5-flash-lite", "gemini-2.0-flash"]))
    errors: list[str] = []

    for candidate in candidate_models:
        try:
            response = client.models.generate_content(
                model=candidate,
                contents=prompt,
                config=config,
            )
            text = _clean_spoken_script(getattr(response, "text", "") or "")
            word_count = len(text.split())
            if word_count >= 15:
                return text
            errors.append(f"{candidate}: returned empty or too-short script ({word_count} words)")
        except Exception as exc:
            redacted = _redact_secret(str(exc), resolved_key) or exc.__class__.__name__
            errors.append(f"{candidate}: {redacted}")

    raise ScriptGenerationError(f"AI script generation failed ({'; '.join(errors)}).")
