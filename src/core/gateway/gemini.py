"""Google Gemini Direct REST provider."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .base import BaseLLMProvider, is_rate_limit_error

logger = logging.getLogger(__name__)

_GEMINI_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class GeminiProvider(BaseLLMProvider):
    """Direct Google Gemini REST provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model or DEFAULT_GEMINI_MODEL,
        )

    def _generate_url(self, model: str) -> str:
        return _GEMINI_GENERATE_URL.format(model=model, key=self.api_key)

    def generate(
        self,
        prompt: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Synchronous chat completion via Gemini Direct REST API."""
        if not self.is_available():
            raise ValueError("GEMINI_API_KEY is not configured.")

        target_model = model or self.model or DEFAULT_GEMINI_MODEL
        url = self._generate_url(target_model)

        generation_config: Dict[str, Any] = {
            "temperature": temperature,
        }
        if json_mode:
            generation_config["responseMimeType"] = "application/json"

        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }

        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        try:
            res = self._post_json(
                url=url,
                payload=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            candidates = res.get("candidates", [])
            if not candidates:
                raise ValueError(f"No candidates returned from Gemini: {res}")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ValueError(f"No content parts returned in candidate: {candidates[0]}")

            return parts[0].get("text", "")
        except Exception as e:
            if is_rate_limit_error(e):
                logger.warning("Gemini rate limited: %s", e)
                try:
                    from src.core.db.error_log import log_error
                    log_error(
                        source="gateway",
                        component="gemini_provider",
                        error_type="RATE_LIMIT",
                        message=f"Gemini rate limited: {e}",
                    )
                except Exception:
                    pass
                raise RuntimeError(f"Gemini rate limited: {e}") from e
            raise
