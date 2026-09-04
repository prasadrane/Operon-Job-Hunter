"""Base Discovery Agent with telemetry and resilience boundaries."""

import logging
from typing import Any, Dict, List, Optional
from src.core.models import JobPosting

log = logging.getLogger(__name__)


def canonicalize_url(raw_url: str) -> str:
    """Strip query parameters and trailing slashes for rock-solid URL deduplication."""
    if not raw_url:
        return ""
    clean = raw_url.split("?")[0].split("#")[0].rstrip("/")
    return clean


class BaseDiscoveryAgent:
    """Base class for all specialized discovery subagents."""

    def __init__(self, name: str, codename: str, timeout: float = 15.0) -> None:
        self.name = name
        self.codename = codename
        self.timeout = timeout
        self.total_discovered = 0

    def log_action(self, msg: str) -> None:
        log.info("[%s - %s] %s", self.codename, self.name, msg)
