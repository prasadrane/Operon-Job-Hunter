"""Multi-provider LLM gateway package with failover orchestration."""

from .base import BaseLLMProvider, is_fatal_http_error, is_rate_limit_error
from .gemini import GeminiProvider
from .openrouter import OpenRouterProvider
from .alibaba import AlibabaProvider
from .facade import LLMGateway, get_gateway

__all__ = [
    "BaseLLMProvider",
    "GeminiProvider",
    "OpenRouterProvider",
    "AlibabaProvider",
    "LLMGateway",
    "get_gateway",
    "is_rate_limit_error",
    "is_fatal_http_error",
]
