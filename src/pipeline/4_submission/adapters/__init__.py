"""ATS Adapters package and dispatcher."""

from typing import Any, List, Optional

from .base_adapter import (
    BaseATSAdapter,
    CONFIRMATION_INDICATORS,
    CONFIRMATION_URL_KEYWORDS,
)
from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter
from .ashby import AshbyAdapter
from .workday import WorkdayAdapter
from .workday_agentic import WorkdayAgenticSubmitter
from .generic import GenericAdapter


ATS_ADAPTERS: List[BaseATSAdapter] = [
    GreenhouseAdapter(),
    LeverAdapter(),
    AshbyAdapter(),
    WorkdayAgenticSubmitter(),  # Multi-step wizard handler — checked before basic WorkdayAdapter
    WorkdayAdapter(),
    GenericAdapter(),
]


def get_adapter(url: str, page: Optional[Any] = None) -> BaseATSAdapter:
    """Return the most specific ATS adapter for a given URL and page context."""
    for adapter in ATS_ADAPTERS:
        try:
            if not isinstance(adapter, GenericAdapter) and adapter.can_handle(url, page):
                return adapter
        except Exception:
            continue
    # Default fallback
    return GenericAdapter()


__all__ = [
    "BaseATSAdapter",
    "CONFIRMATION_INDICATORS",
    "CONFIRMATION_URL_KEYWORDS",
    "GreenhouseAdapter",
    "LeverAdapter",
    "AshbyAdapter",
    "WorkdayAdapter",
    "WorkdayAgenticSubmitter",
    "GenericAdapter",
    "ATS_ADAPTERS",
    "get_adapter",
]
