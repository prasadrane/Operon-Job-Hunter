"""LLM Gateway Facade: Multi-provider failover chain and orchestration."""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from src.core.config import Settings, get_settings
from .alibaba import AlibabaProvider
from .base import BaseLLMProvider, is_rate_limit_error
from .gemini import GeminiProvider
from .openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)


def _is_empty_response(res: Any) -> bool:
    return isinstance(res, str) and res.strip() == ""


class LLMGateway:
    """Multi-provider LLM gateway orchestrating automatic failover.

    Default failover order:
      1. Google Gemini Direct REST (fast, primary)
      2. OpenRouter free/budget pool (fallback 1)
      3. Alibaba DashScope (fallback 2)
    """

    def __init__(
        self,
        gemini_provider: Optional[GeminiProvider] = None,
        openrouter_provider: Optional[OpenRouterProvider] = None,
        alibaba_provider: Optional[AlibabaProvider] = None,
        mock_provider: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        cfg = settings or get_settings()
        self.settings = cfg
        self.mock_provider = mock_provider
        self.gemini_provider = gemini_provider or GeminiProvider(
            api_key=cfg.gemini_api_key
        )
        self.openrouter_provider = openrouter_provider or OpenRouterProvider(
            api_key=cfg.openrouter_api_key
        )
        self.alibaba_provider = alibaba_provider or AlibabaProvider(
            api_key=cfg.alibaba_api_key,
            model=cfg.alibaba_model,
            base_url=cfg.alibaba_base_url,
        )

    @property
    def providers(self) -> List[BaseLLMProvider]:
        """Ordered list of providers for failover chain respecting primary_llm_provider."""
        primary = getattr(self.settings, "primary_llm_provider", "alibaba").lower()
        if primary == "mock":
            from src.core.gateway.mock import MockLLMProvider
            return [self.mock_provider or MockLLMProvider()]
        if primary == "alibaba":
            return [
                self.alibaba_provider,
                self.gemini_provider,
                self.openrouter_provider,
            ]
        elif primary == "openrouter":
            return [
                self.openrouter_provider,
                self.alibaba_provider,
                self.gemini_provider,
            ]
        else:
            return [
                self.gemini_provider,
                self.alibaba_provider,
                self.openrouter_provider,
            ]

    def generate(
        self,
        prompt: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Generate text completion using the resilient failover chain."""
        last_error: Optional[Exception] = None

        for provider in self.providers:
            provider_name = provider.__class__.__name__
            try:
                logger.debug("Attempting generation with provider %s", provider_name)
                res = provider.generate(
                    prompt=prompt,
                    json_mode=json_mode,
                    temperature=temperature,
                    system_prompt=system_prompt,
                    model=model,
                )

                if _is_empty_response(res):
                    logger.warning(
                        "Provider %s returned an empty response. Failing over to next provider.",
                        provider_name,
                    )
                    continue

                return res
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Provider %s failed with error: %s. Failing over to next provider.",
                    provider_name,
                    exc,
                )
                try:
                    from src.core.db.error_log import log_error
                    log_error(
                        source="gateway",
                        component=f"{provider_name}_provider",
                        error_type="PROVIDER_ERROR",
                        message=f"Provider {provider_name} failed: {exc}. Failing over.",
                        metadata={"provider": provider_name},
                    )
                except Exception:
                    pass
                continue

        error_msg = f"All providers in the fallback chain failed. Last error: {last_error}"
        logger.error(error_msg)
        try:
            from src.core.db.error_log import log_error
            log_error(
                source="gateway",
                component="llm_gateway",
                error_type="FATAL",
                message=error_msg,
            )
        except Exception:
            pass
        raise RuntimeError("All providers in the fallback chain failed.") from last_error


# Module-level singleton
_GATEWAY_INSTANCE: Optional[LLMGateway] = None


def get_gateway(settings: Optional[Settings] = None) -> LLMGateway:
    """Return or create a singleton LLMGateway instance."""
    global _GATEWAY_INSTANCE
    if settings is not None:
        return LLMGateway(settings=settings)
    if _GATEWAY_INSTANCE is None:
        _GATEWAY_INSTANCE = LLMGateway()
    return _GATEWAY_INSTANCE
