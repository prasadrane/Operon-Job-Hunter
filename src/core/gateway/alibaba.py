"""Alibaba Cloud DashScope provider."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseLLMProvider, is_rate_limit_error

logger = logging.getLogger(__name__)

DEFAULT_ALIBABA_URL = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_ALIBABA_MODEL = "qwen3.6-flash"



class AlibabaProvider(BaseLLMProvider):
    """Alibaba DashScope provider supporting OpenAI-compatible and Anthropic-compatible endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model or DEFAULT_ALIBABA_MODEL,
            base_url=base_url or DEFAULT_ALIBABA_URL,
        )

    def _is_anthropic_endpoint(self) -> bool:
        return bool(self.base_url and "/messages" in self.base_url)

    def _headers(self) -> Dict[str, str]:
        if self._is_anthropic_endpoint():
            return {
                "x-api-key": self.api_key or "",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(
        self,
        prompt: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
    ) -> str:
        """Synchronous chat completion via Alibaba DashScope."""
        if not self.is_available():
            raise ValueError("ALIBABA_API_KEY is not configured.")

        target_model = model or self.model or DEFAULT_ALIBABA_MODEL
        target_url = self.base_url or DEFAULT_ALIBABA_URL

        if self._is_anthropic_endpoint():
            payload: Dict[str, Any] = {
                "model": target_model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            }
            if system_prompt:
                payload["system"] = system_prompt
        else:
            messages: List[Dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

        try:
            res = self._post_json(
                url=target_url,
                payload=payload,
                headers=self._headers(),
                timeout=timeout,
            )

            # Check for Anthropic-compatible content blocks first if present
            if "content" in res and isinstance(res["content"], list):
                for block in res["content"]:
                    if block.get("type") == "text":
                        return block.get("text", "")
                return ""

            # Standard OpenAI-compatible choices format
            choices = res.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")

            raise ValueError(f"Unexpected response format from Alibaba: {res}")
        except Exception as e:
            if is_rate_limit_error(e):
                logger.warning("Alibaba rate limited: %s", e)
                try:
                    from src.core.db.error_log import log_error
                    log_error(
                        source="gateway",
                        component="alibaba_provider",
                        error_type="RATE_LIMIT",
                        message=f"Alibaba rate limited: {e}",
                    )
                except Exception:
                    pass
                raise RuntimeError(f"Alibaba rate limited: {e}") from e
            raise
