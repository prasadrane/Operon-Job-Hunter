"""Base provider abstraction and shared utilities for LLM API calls."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

RATE_LIMIT_TAGS: List[str] = [
    "429",
    "rate limit",
    "rate_limit",
    "quota",
    "resource_exhausted",
    "too many requests",
    "throttled",
    "exceeded your current quota",
    "tokens per minute",
    "requests per minute",
]


def is_rate_limit_error(err: BaseException | Exception | str) -> bool:
    """Return True when err represents a rate-limit / throttling error."""
    err_str = str(err).lower()
    if any(tag in err_str for tag in RATE_LIMIT_TAGS):
        return True
    status = getattr(err, "status_code", None) or getattr(err, "code", None)
    if status is not None:
        try:
            return int(status) == 429
        except (ValueError, TypeError):
            pass
    return False


def is_fatal_http_error(err: BaseException) -> bool:
    """Check if an error is a non-retryable client HTTP error (400, 401, 403, 404, 422)."""
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    if isinstance(code, int) and code in {400, 401, 403, 404, 422}:
        return True
    err_str = str(err).lower()
    for status in ["400", "401", "403", "404", "422"]:
        if f"http error {status}" in err_str or f"status {status}" in err_str or f"error code: {status}" in err_str:
            return True
    return False


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def is_available(self) -> bool:
        """Check if provider has credentials configured."""
        return bool(self.api_key and self.api_key.strip())

    @abstractmethod
    def generate(
        self,
        prompt: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Synchronous text generation completion."""
        ...

    def _post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Perform a synchronous POST request via urllib and parse JSON response."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                return json.loads(resp_body)
        except urllib.error.HTTPError as http_err:
            try:
                error_content = http_err.read().decode("utf-8")
            except Exception:
                error_content = str(http_err)
            raise RuntimeError(
                f"HTTP error {http_err.code} calling {url}: {error_content}"
            ) from http_err
        except Exception as e:
            raise RuntimeError(f"Network error calling {url}: {e}") from e
