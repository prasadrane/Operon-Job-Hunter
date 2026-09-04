"""OpenRouter LLM provider (OpenAI-compatible protocol)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseLLMProvider, is_rate_limit_error

logger = logging.getLogger(__name__)

OPENROUTER_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-chat"


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter provider calling chat completions endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model or DEFAULT_OPENROUTER_MODEL,
            base_url=base_url or OPENROUTER_COMPLETIONS_URL,
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/careergraph-ai",
            "X-Title": "CareerGraph AI",
        }

    def generate(
        self,
        prompt: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Synchronous chat completion via OpenRouter."""
        if not self.is_available():
            raise ValueError("OPENROUTER_API_KEY is not configured.")

        target_model = model or self.model or DEFAULT_OPENROUTER_MODEL
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            res = self._post_json(
                url=self.base_url or OPENROUTER_COMPLETIONS_URL,
                payload=payload,
                headers=self._headers(),
                timeout=30,
            )
            choices = res.get("choices", [])
            if not choices:
                raise ValueError(f"No choices returned from OpenRouter: {res}")

            message = choices[0].get("message", {})
            return message.get("content", "")
        except Exception as e:
            if is_rate_limit_error(e):
                logger.warning("OpenRouter rate limited: %s", e)
                try:
                    from src.core.db.error_log import log_error
                    log_error(
                        source="gateway",
                        component="openrouter_provider",
                        error_type="RATE_LIMIT",
                        message=f"OpenRouter rate limited: {e}",
                    )
                except Exception:
                    pass
                raise RuntimeError(f"OpenRouter rate limited: {e}") from e
            raise
