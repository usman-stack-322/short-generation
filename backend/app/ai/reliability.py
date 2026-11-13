"""Bounded Gemini availability retries shared by script and SEO generation."""
import logging
import random
import time
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiGenerationError(RuntimeError):
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def safe_detail(value):
    text = str(value)
    for secret in (settings.gemini_api_key, settings.google_client_secret, settings.elevenlabs_api_key):
        if secret:
            text = text.replace(secret, '[REDACTED]')
    return text[:2000]


class GeminiRetryPolicy:
    def __init__(self):
        self.attempts = 0
        self.fallback_used = False
        self.model_used = settings.gemini_model

    def execute(self, request, prompt, primary_model=None):
        selected_model=primary_model or settings.gemini_model
        self.attempts, self.fallback_used, self.model_used = 0, False, selected_model
        malformed = 0
        for attempt in range(3):
            try:
                return self._attempt(request, prompt, selected_model, False)
            except GeminiGenerationError as exc:
                if not exc.retryable:
                    raise
                if attempt < 2:
                    time.sleep((2, 5)[attempt] + random.uniform(0, .25))
                    continue
                fallbacks = []
                for cand in (settings.gemini_fallback_model.strip(), settings.gemini_model.strip()):
                    if cand and cand != selected_model and cand not in fallbacks:
                        fallbacks.append(cand)
                last_exc = exc
                for fb in fallbacks:
                    try:
                        return self._fallback(request, prompt, fb)
                    except GeminiGenerationError as fb_exc:
                        last_exc = fb_exc
                        if not fb_exc.retryable:
                            raise
                raise last_exc
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                malformed += 1
                logger.warning('Gemini malformed structured output model=%s attempt=%s detail=%r',
                               self.model_used, self.attempts, safe_detail(exc))
                if malformed >= 2 or attempt == 2:
                    raise GeminiGenerationError('Gemini returned invalid structured output. Please retry generation.', retryable=True) from None
                prompt += '\nReturn valid JSON containing every requested field.'
        raise AssertionError('Gemini retry bound exceeded')

    def _fallback(self, request, prompt, model):
        for fb_attempt in range(2):
            try:
                return self._attempt(request, prompt, model, True)
            except GeminiGenerationError as exc:
                if not exc.retryable or fb_attempt:
                    raise
                time.sleep(2 + random.uniform(0, .25))
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                logger.warning('Gemini fallback malformed output model=%s detail=%r', model, safe_detail(exc))
                raise GeminiGenerationError('Gemini returned invalid structured output. Please retry generation.', retryable=True) from None

    def _attempt(self, request, prompt, model, fallback):
        self.attempts += 1
        self.model_used, self.fallback_used = model, fallback
        try:
            return request(prompt, model, fallback)
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            try:
                error = exc.response.json().get('error', {})
                status, detail = error.get('status', ''), error.get('message', '')
            except (ValueError, AttributeError, TypeError):
                status, detail = '', exc.response.text[:2000]
            logger.warning('Gemini API error model=%s attempt=%s http=%s api_status=%s detail=%r',
                           model, self.attempts, code, safe_detail(status), safe_detail(detail))
            if code in {500, 502, 503, 504}:
                raise GeminiGenerationError(
                    'Gemini is temporarily unavailable because of high demand. Please retry generation.', retryable=True) from None
            if code in {401, 403}:
                message = 'Gemini authentication or permission was rejected. Check the backend API key and account permissions.'
            elif code == 404:
                message = 'The configured Gemini model is unavailable for this API/account. Check GEMINI_MODEL.'
            elif code == 429:
                message = 'Gemini quota or rate limit was reached. Check your account limits before retrying.'
            else:
                message = 'Gemini rejected the request. Check the backend provider configuration.'
            raise GeminiGenerationError(message) from None
        except httpx.TransportError as exc:
            logger.warning('Gemini network error model=%s attempt=%s type=%s', model, self.attempts, type(exc).__name__)
            raise GeminiGenerationError('Gemini is temporarily unavailable. Please retry generation.', retryable=True) from None
