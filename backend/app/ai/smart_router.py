"""Multi-model, multi-key, and multi-provider AI router with cooldown tracking and structured JSON repair."""
import hashlib
import json
import logging
import re
import threading
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class AIProviderError(ValueError):
    """Structured AI invocation failure with secrets redacted."""


class QuotaExhaustedError(AIProviderError):
    """Raised when every configured model/key/provider is rate-limited or quota-exhausted."""


_LOCK = threading.Lock()
_COOLDOWNS: dict[str, dict] = {}
_PROMPT_CACHE: dict[str, tuple[float, dict]] = {}
_LAST_SUCCESS: dict[str, str] = {"provider": "", "model": "", "at": ""}
_LAST_ERROR: str = ""
_CACHE_TTL_SECONDS = 1800
_MAX_CACHE_ITEMS = 200


def parse_gemini_keys() -> list[str]:
    """Return deduplicated non-empty Gemini API keys across single and multi-key settings."""
    raw = f"{settings.gemini_api_key or ''}\n{getattr(settings, 'gemini_api_keys', '') or ''}"
    keys: list[str] = []
    for token in re.split(r"[\s,;]+", raw.strip()):
        tok = token.strip()
        if tok and tok not in keys:
            keys.append(tok)
    return keys


def gemini_model_cascade(primary_model: str | None = None) -> list[str]:
    """Return ordered deduplicated Gemini/Gemma models from primary through fallback list."""
    raw_candidates = [
        (primary_model or "").strip(),
        (settings.gemini_model or "").strip(),
        (settings.gemini_fallback_model or "").strip(),
        *[
            m.strip()
            for m in (getattr(settings, "gemini_fallback_models", "") or "").split(",")
            if m.strip()
        ],
    ]
    models: list[str] = []
    for item in raw_candidates:
        if item and item not in models:
            models.append(item)
    return models or ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemma-3-27b-it"]


def has_any_ai_configured() -> bool:
    """True when at least one AI provider (Gemini, Groq, OpenAI-compat, or explicit Ollama) is configured."""
    return bool(
        parse_gemini_keys()
        or (getattr(settings, "groq_api_key", "") or "").strip()
        or (
            (getattr(settings, "openai_compat_base_url", "") or "").strip()
            and (getattr(settings, "openai_compat_model", "") or "").strip()
        )
        or (getattr(settings, "ollama_model", "") or "").strip()
    )


def redact_secrets(text: object) -> str:
    """Strip configured secrets before logging or surfacing details."""
    msg = str(text)
    secrets_to_hide = [
        *parse_gemini_keys(),
        settings.google_client_secret,
        settings.elevenlabs_api_key,
        getattr(settings, "groq_api_key", ""),
        getattr(settings, "openai_compat_api_key", ""),
    ]
    for secret in secrets_to_hide:
        if secret and len(secret) > 4:
            msg = msg.replace(secret, "[REDACTED]")
    return msg[:2000]


def _key_hint(key: str) -> str:
    if len(key) <= 8:
        return "key"
    return f"...{key[-4:]}"


def _slot_key(provider: str, hint: str, model: str) -> str:
    return f"{provider}:{hint}:{model}"


def clear_cooldowns() -> None:
    with _LOCK:
        _COOLDOWNS.clear()


def _mark_cooldown(slot: str, seconds: float, reason: str) -> None:
    until = time.time() + max(5.0, float(seconds))
    with _LOCK:
        _COOLDOWNS[slot] = {"until": until, "reason": reason[:200]}


def _is_cooled_down(slot: str) -> bool:
    now = time.time()
    with _LOCK:
        entry = _COOLDOWNS.get(slot)
        if not entry:
            return False
        if now >= entry["until"]:
            _COOLDOWNS.pop(slot, None)
            return False
        return True


def _parse_retry_seconds(detail: str, retry_after_header: str | None = None) -> float | None:
    if retry_after_header:
        try:
            return float(retry_after_header)
        except ValueError:
            pass
    m = re.search(
        r"retry\s+in\s+(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+(?:\.\d+)?)s)?",
        detail,
        re.I,
    )
    if not m or not any(m.groups()):
        return None
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = float(m.group(3) or 0.0)
    return hours * 3600.0 + minutes * 60.0 + seconds


def _extract_json_text(raw: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I).strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _schema_instruction(schema: type[BaseModel]) -> str:
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return (
        "\n\nRESPONSE FORMAT REQUIREMENT:\n"
        "Return ONLY a single valid JSON object (no markdown fences, no commentary) matching this exact JSON Schema:\n"
        f"{schema_json}"
    )


def _validate_response(raw_text: str, schema: type[T]) -> dict:
    candidate = _extract_json_text(raw_text)
    return schema.model_validate_json(candidate).model_dump()


def _detect_ollama_model() -> str | None:
    configured = (getattr(settings, "ollama_model", "") or "").strip()
    if configured:
        return configured
    if not getattr(settings, "ai_auto_detect_ollama", True):
        return None
    base = (getattr(settings, "ollama_base_url", "") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        r = httpx.get(f"{base}/api/tags", timeout=0.6, trust_env=False)
        if r.status_code != 200:
            return None
        models = [m.get("name") for m in r.json().get("models", []) if m.get("name")]
        return models[0] if models else None
    except Exception:
        return None


def _call_gemini(prompt: str, schema: type[T], key: str, model: str, force_prompt_json: bool = False) -> dict:
    use_json_schema = not force_prompt_json and "gemma" not in model.lower()
    text_prompt = prompt if use_json_schema else prompt + _schema_instruction(schema)
    gen_cfg = (
        {"responseMimeType": "application/json", "responseJsonSchema": schema.model_json_schema()}
        if use_json_schema
        else {"temperature": 0.2}
    )
    resp = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key},
        json={"contents": [{"parts": [{"text": text_prompt}]}], "generationConfig": gen_cfg},
        timeout=35,
        trust_env=False,
    )
    resp.raise_for_status()
    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _validate_response(raw, schema)


def _call_openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    schema: type[T],
) -> dict:
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    messages = [
        {
            "role": "system",
            "content": "You produce strict, concise valid JSON matching the requested schema without markdown fences.",
        },
        {"role": "user", "content": prompt + _schema_instruction(schema)},
    ]
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=45, trust_env=False)
    if resp.status_code == 400 and "response_format" in resp.text.lower():
        payload.pop("response_format", None)
        resp = httpx.post(url, headers=headers, json=payload, timeout=45, trust_env=False)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    return _validate_response(raw, schema)


def _call_ollama(base_url: str, model: str, prompt: str, schema: type[T]) -> dict:
    url = base_url.rstrip("/") + "/api/chat"
    resp = httpx.post(
        url,
        json={
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": "Output only valid JSON matching the requested schema."},
                {"role": "user", "content": prompt + _schema_instruction(schema)},
            ],
        },
        timeout=60,
        trust_env=False,
    )
    resp.raise_for_status()
    raw = resp.json()["message"]["content"]
    return _validate_response(raw, schema)


def run_structured_ai(
    prompt: str,
    schema: type[T],
    *,
    primary_model: str | None = None,
    cacheable: bool = False,
) -> dict:
    """Execute a structured JSON AI call with automatic multi-model, multi-key, and backup-provider failover."""
    global _LAST_ERROR
    cache_key = ""
    if cacheable:
        cache_key = hashlib.sha256(f"{schema.__name__}:{prompt}".encode("utf-8")).hexdigest()
        with _LOCK:
            hit = _PROMPT_CACHE.get(cache_key)
            if hit and (time.time() - hit[0]) < _CACHE_TTL_SECONDS:
                return json.loads(json.dumps(hit[1]))

    gemini_keys = parse_gemini_keys()
    models = gemini_model_cascade(primary_model=primary_model)
    groq_key = (getattr(settings, "groq_api_key", "") or "").strip()
    compat_url = (getattr(settings, "openai_compat_base_url", "") or "").strip()
    compat_key = (getattr(settings, "openai_compat_api_key", "") or "").strip()
    compat_model = (getattr(settings, "openai_compat_model", "") or "").strip()
    ollama_url = (getattr(settings, "ollama_base_url", "") or "").strip()
    ollama_model = _detect_ollama_model()

    if not gemini_keys and not groq_key and not (compat_url and compat_model) and not ollama_model:
        raise ValueError(
            "Configure GEMINI_API_KEY (or GROQ_API_KEY / Ollama in Settings) for title analysis, grounded scripts and scene regeneration."
        )

    saw_quota = False
    saw_auth = False
    last_message = "No AI provider succeeded."

    def record_success(provider: str, model_name: str, data: dict) -> dict:
        global _LAST_ERROR
        with _LOCK:
            _LAST_SUCCESS.update({"provider": provider, "model": model_name, "at": time.strftime("%H:%M:%S")})
            _LAST_ERROR = ""
            if cacheable and cache_key:
                if len(_PROMPT_CACHE) >= _MAX_CACHE_ITEMS:
                    oldest = min(_PROMPT_CACHE, key=lambda k: _PROMPT_CACHE[k][0])
                    _PROMPT_CACHE.pop(oldest, None)
                _PROMPT_CACHE[cache_key] = (time.time(), data)
        return data

    def invoke_with_repair(call_fn, provider: str, model_name: str) -> dict:
        try:
            return call_fn(prompt)
        except (ValueError, ValidationError, KeyError, IndexError, TypeError) as exc:
            repair_prompt = (
                f"{prompt}\n\nREPAIR PREVIOUS INVALID JSON ({redact_secrets(exc)[:300]}). "
                "Ensure every required field matches the schema exactly and strings respect length bounds."
            )
            return call_fn(repair_prompt)

    # Tier 1: Gemini & Gemma cascade across all configured keys (best quality models first)
    bad_key_hints: set[str] = set()
    for model in models:
        for key in gemini_keys:
            hint = _key_hint(key)
            if hint in bad_key_hints:
                continue
            slot = _slot_key("gemini", hint, model)
            if _is_cooled_down(slot):
                saw_quota = True
                continue
            force_prompt_json = False
            for attempt in range(2):
                try:
                    data = invoke_with_repair(
                        lambda p: _call_gemini(p, schema, key, model, force_prompt_json=force_prompt_json),
                        "gemini",
                        model,
                    )
                    return record_success("gemini", model, data)
                except httpx.HTTPStatusError as exc:
                    code = exc.response.status_code
                    try:
                        err = exc.response.json().get("error", {})
                        status_str = err.get("status", "")
                        detail = err.get("message", "") or exc.response.text
                    except Exception:
                        status_str, detail = "", exc.response.text
                    safe_msg = redact_secrets(detail)
                    logger.warning(
                        "Gemini cascade error provider=gemini key=%s model=%s http=%s status=%s detail=%r",
                        hint, model, code, status_str, safe_msg[:400],
                    )
                    if code == 429 or "RESOURCE_EXHAUSTED" in status_str.upper():
                        saw_quota = True
                        wait_s = _parse_retry_seconds(safe_msg, exc.response.headers.get("Retry-After"))
                        # Short burst RPM pause ONLY if tiny wait and no retry done yet
                        if wait_s is not None and wait_s <= 4.0 and attempt == 0:
                            time.sleep(wait_s + 0.3)
                            continue
                        cooldown = min(max(wait_s or 180.0, 90.0), 900.0)
                        _mark_cooldown(slot, cooldown, f"429 rate/quota limit on {model}")
                        last_message = "Gemini quota or rate limit was reached across configured models."
                        break
                    if code == 400 and ("json mode" in safe_msg.lower() or "schema" in safe_msg.lower()) and not force_prompt_json:
                        force_prompt_json = True
                        continue
                    if code in {401, 403}:
                        saw_auth = True
                        bad_key_hints.add(hint)
                        _mark_cooldown(slot, 3600, f"HTTP {code} auth rejected")
                        last_message = "Gemini authentication or permission was rejected."
                        break
                    if code in {404, 400}:
                        _mark_cooldown(slot, 3600, f"HTTP {code} model unavailable")
                        last_message = f"Model {model} unavailable ({code}); cascaded."
                        break
                    if code in {500, 502, 503, 504}:
                        if attempt == 0:
                            time.sleep(1.5)
                            continue
                        _mark_cooldown(slot, 45, f"HTTP {code} server overload")
                        last_message = "Gemini temporarily overloaded."
                        break
                    break
                except httpx.TransportError as exc:
                    logger.warning("Gemini network error model=%s type=%s", model, type(exc).__name__)
                    if attempt == 0:
                        time.sleep(1.0)
                        continue
                    _mark_cooldown(slot, 30, f"Network {type(exc).__name__}")
                    last_message = "Gemini network timeout."
                    break
                except (ValueError, ValidationError, KeyError, IndexError, TypeError) as exc:
                    logger.warning("Gemini structured output invalid model=%s detail=%r", model, redact_secrets(exc)[:300])
                    last_message = "Gemini returned invalid structured output."
                    break

    # Tier 2: Groq Free Tier (OpenAI-compatible fast inference, ~1000+ RPD free)
    if groq_key:
        groq_model = (getattr(settings, "groq_model", "") or "llama-3.3-70b-versatile").strip()
        groq_slot = _slot_key("groq", _key_hint(groq_key), groq_model)
        if not _is_cooled_down(groq_slot):
            try:
                data = invoke_with_repair(
                    lambda p: _call_openai_compat("https://api.groq.com/openai/v1", groq_key, groq_model, p, schema),
                    "groq",
                    groq_model,
                )
                return record_success("groq", groq_model, data)
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code == 429:
                    saw_quota = True
                    _mark_cooldown(groq_slot, 180, "Groq 429 limit")
                else:
                    _mark_cooldown(groq_slot, 300, f"Groq HTTP {code}")
                logger.warning("Groq backup failed http=%s detail=%r", code, redact_secrets(exc.response.text)[:300])
            except Exception as exc:
                logger.warning("Groq backup error type=%s detail=%r", type(exc).__name__, redact_secrets(exc)[:300])

    # Tier 3: Custom OpenAI-Compatible Endpoint (OpenRouter :free, Cerebras, LM Studio, etc.)
    if compat_url and compat_model:
        compat_slot = _slot_key("openai_compat", "custom", compat_model)
        if not _is_cooled_down(compat_slot):
            try:
                data = invoke_with_repair(
                    lambda p: _call_openai_compat(compat_url, compat_key, compat_model, p, schema),
                    "openai_compat",
                    compat_model,
                )
                return record_success("openai_compat", compat_model, data)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    saw_quota = True
                    _mark_cooldown(compat_slot, 180, "OpenAI-compat 429")
                else:
                    _mark_cooldown(compat_slot, 300, f"HTTP {exc.response.status_code}")
                logger.warning("OpenAI-compat backup failed http=%s", exc.response.status_code)
            except Exception as exc:
                logger.warning("OpenAI-compat backup error type=%s detail=%r", type(exc).__name__, redact_secrets(exc)[:300])

    # Tier 4: Local Ollama (Unlimited 0-quota offline fallback when installed/running)
    if ollama_url and ollama_model:
        try:
            data = invoke_with_repair(
                lambda p: _call_ollama(ollama_url, ollama_model, p, schema),
                "ollama",
                ollama_model,
            )
            return record_success("ollama", ollama_model, data)
        except Exception as exc:
            logger.warning("Ollama backup error model=%s detail=%r", ollama_model, redact_secrets(exc)[:300])

    _LAST_ERROR = last_message
    if saw_quota:
        raise QuotaExhaustedError(
            "AI rate/daily quota limit was reached across configured Gemini models. Add a free Groq key, extra Gemini key, or local Ollama in Settings -> AI Providers."
        )
    if saw_auth and not groq_key and not ollama_model:
        raise AIProviderError("Gemini authentication or permission was rejected. Check API keys in Settings or backend/.env.")
    raise AIProviderError(f"{last_message} Please retry generation.")


def get_ai_status() -> dict:
    """Return secret-free status of configured AI providers, fallback cascade, and active cooldowns."""
    keys = parse_gemini_keys()
    models = gemini_model_cascade()
    now = time.time()
    with _LOCK:
        active_cooldowns = [
            {
                "slot": slot,
                "remaining_seconds": round(max(0.0, info["until"] - now)),
                "reason": info["reason"],
            }
            for slot, info in _COOLDOWNS.items()
            if info["until"] > now
        ]
        last_success = dict(_LAST_SUCCESS)
        last_err = _LAST_ERROR
    ollama_detected = _detect_ollama_model()
    return {
        "gemini_configured": bool(keys),
        "gemini_key_count": len(keys),
        "gemini_key_hints": [_key_hint(k) for k in keys],
        "gemini_primary_model": models[0] if models else "",
        "gemini_cascade_models": models,
        "groq_configured": bool((getattr(settings, "groq_api_key", "") or "").strip()),
        "groq_model": getattr(settings, "groq_model", "llama-3.3-70b-versatile"),
        "openai_compat_configured": bool(
            (getattr(settings, "openai_compat_base_url", "") or "").strip()
            and (getattr(settings, "openai_compat_model", "") or "").strip()
        ),
        "openai_compat_base_url": getattr(settings, "openai_compat_base_url", ""),
        "openai_compat_model": getattr(settings, "openai_compat_model", ""),
        "ollama_base_url": getattr(settings, "ollama_base_url", "http://127.0.0.1:11434"),
        "ollama_configured": bool((getattr(settings, "ollama_model", "") or "").strip()),
        "ollama_detected_model": ollama_detected or "",
        "active_cooldowns": active_cooldowns,
        "last_success": last_success,
        "last_error": last_err,
    }


def test_ai_providers() -> dict:
    """Probe each configured provider/model to report live health without throwing."""

    class Ping(BaseModel):
        ok: bool

    results: list[dict] = []
    for model in gemini_model_cascade():
        for idx, key in enumerate(parse_gemini_keys(), start=1):
            hint = _key_hint(key)
            slot = _slot_key("gemini", hint, model)
            if _is_cooled_down(slot):
                results.append({"provider": "gemini", "key": hint, "model": model, "status": "cooled_down"})
                continue
            try:
                _call_gemini('Return {"ok": true}', Ping, key, model)
                results.append({"provider": "gemini", "key": hint, "model": model, "status": "ok"})
            except httpx.HTTPStatusError as exc:
                results.append({
                    "provider": "gemini",
                    "key": hint,
                    "model": model,
                    "status": f"http_{exc.response.status_code}",
                })
            except Exception as exc:
                results.append({"provider": "gemini", "key": hint, "model": model, "status": type(exc).__name__})

    groq_key = (getattr(settings, "groq_api_key", "") or "").strip()
    if groq_key:
        gm = getattr(settings, "groq_model", "llama-3.3-70b-versatile")
        try:
            _call_openai_compat("https://api.groq.com/openai/v1", groq_key, gm, 'Return {"ok": true}', Ping)
            results.append({"provider": "groq", "key": _key_hint(groq_key), "model": gm, "status": "ok"})
        except httpx.HTTPStatusError as exc:
            results.append({"provider": "groq", "key": _key_hint(groq_key), "model": gm, "status": f"http_{exc.response.status_code}"})
        except Exception as exc:
            results.append({"provider": "groq", "key": _key_hint(groq_key), "model": gm, "status": type(exc).__name__})

    om = _detect_ollama_model()
    if om:
        try:
            _call_ollama(getattr(settings, "ollama_base_url", "http://127.0.0.1:11434"), om, 'Return {"ok": true}', Ping)
            results.append({"provider": "ollama", "key": "local", "model": om, "status": "ok"})
        except Exception as exc:
            results.append({"provider": "ollama", "key": "local", "model": om, "status": type(exc).__name__})

    return {"checks": results, "summary": get_ai_status()}

