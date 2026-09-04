"""RoutingEngine — T1/T2/T3 tier selection for Stage 4 submission pipeline.

Given a portal_type, URL, and optional page context, decides which submission
tier handles the job:
  T1: FastPath   — deterministic DOM autofill for known ATS platforms
  T2: BrowserUse — LLM-driven browser automation for unknown/novel portals
  T3: WebSurfer  — rule-based visual fallback (last resort)

Routing rules:
  1. portal_type in known_ats AND t1_enabled → T1
  2. portal unknown/generic AND t2_enabled → T2
  3. T1 not available → T2 (if enabled)
  4. T3 as final fallback (if enabled)
  5. All disabled → TierExhaustedError
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.core.config import get_settings

logger = logging.getLogger(__name__)

# Import TierExhaustedError from sibling module (digit-dir requires importlib)
_bua_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
TierExhaustedError = _bua_mod.TierExhaustedError


# ── URL Detection Patterns ────────────────────────────────────────────────────
# Simple substring matching consistent with existing adapters.

_URL_PATTERNS: dict[str, list[str]] = {
    "greenhouse": ["greenhouse.io"],
    "lever": ["lever.co", "jobs.lever.co"],
    "ashby": ["ashbyhq.com", "jobs.ashbyhq.com"],
    "workday": ["myworkdayjobs.com", "myworkday"],
}


def detect_portal_from_url(url: str) -> str:
    """Detect ATS portal type from URL via substring matching.

    Returns the portal type string (e.g. "greenhouse") or "unknown" if no
    pattern matches.
    """
    url_lower = url.lower()
    for portal, patterns in _URL_PATTERNS.items():
        for pattern in patterns:
            if pattern in url_lower:
                return portal
    return "unknown"


# ── Data Models ───────────────────────────────────────────────────────────────


@dataclass
class TierDecision:
    """Result of a routing decision."""

    tier: str  # "T1" | "T2" | "T3"
    engine_name: str  # "FastPath" | "BrowserUse" | "WebSurfer"
    reason: str  # human-readable reason for routing decision
    fallback_chain: list[str] = field(default_factory=list)


# ── Tier Metadata ─────────────────────────────────────────────────────────────

_TIER_META: dict[str, dict[str, str]] = {
    "T1": {"engine_name": "FastPath"},
    "T2": {"engine_name": "BrowserUse"},
    "T3": {"engine_name": "WebSurfer"},
}

_TIER_ORDER = ["T1", "T2", "T3"]


# ── RoutingEngine ─────────────────────────────────────────────────────────────


class RoutingEngine:
    """Decides which submission tier handles a given job.

    Constructor args override config defaults. Uses getattr() for config
    access so missing attributes don't crash the engine.
    """

    def __init__(
        self,
        t1_enabled: Optional[bool] = None,
        t2_enabled: Optional[bool] = None,
        t3_enabled: Optional[bool] = None,
        known_ats: Optional[set[str]] = None,
    ) -> None:
        settings = get_settings()

        # Config defaults via getattr (safe if attrs don't exist yet)
        self._t1_enabled: bool = (
            t1_enabled
            if t1_enabled is not None
            else getattr(settings, "submission_t1_enabled", True)
        )
        self._t2_enabled: bool = (
            t2_enabled
            if t2_enabled is not None
            else getattr(settings, "submission_t2_enabled", True)
        )
        self._t3_enabled: bool = (
            t3_enabled
            if t3_enabled is not None
            else getattr(settings, "submission_t3_enabled", True)
        )

        self._known_ats: set[str] = known_ats or {
            "greenhouse",
            "lever",
            "ashby",
            "workday",
        }

    # ── Public API ────────────────────────────────────────────────────────

    def select(
        self, portal_type: str, url: str, page: Any = None
    ) -> TierDecision:
        """Select the best tier for the given job.

        Args:
            portal_type: ATS platform identifier (e.g. "greenhouse", "unknown")
            url: Full URL to the job application page
            page: Optional page context (unused in basic routing)

        Returns:
            TierDecision with tier, engine name, reason, and fallback chain

        Raises:
            TierExhaustedError: If all tiers are disabled
        """
        # Detect portal from URL if type is unknown/generic
        effective_type = portal_type.lower().strip()
        if effective_type in ("unknown", "generic", ""):
            detected = detect_portal_from_url(url)
            if detected != "unknown":
                effective_type = detected
                logger.info(
                    "Detected portal type '%s' from URL: %s", detected, url
                )

        # Check if it's a known ATS
        is_known = effective_type in self._known_ats

        # Build ordered list of candidate tiers based on portal type
        # Known ATS → T1 first, then T2, T3 as fallbacks
        # Unknown portal → T2 first, then T3 (T1 not applicable)
        if is_known:
            preferred_order = ["T1", "T2", "T3"]
        else:
            preferred_order = ["T2", "T3"]

        enabled_map = {
            "T1": self._t1_enabled,
            "T2": self._t2_enabled,
            "T3": self._t3_enabled,
        }

        for tier in preferred_order:
            if enabled_map[tier]:
                reason = self._build_reason(tier, effective_type, is_known, url)
                fallback = self._build_fallback_chain(tier)
                return TierDecision(
                    tier=tier,
                    engine_name=_TIER_META[tier]["engine_name"],
                    reason=reason,
                    fallback_chain=fallback,
                )

        raise TierExhaustedError(
            "All submission tiers (T1/T2/T3) are disabled. "
            "Check configuration: submission_t1_enabled, "
            "submission_t2_enabled, submission_t3_enabled"
        )

    def get_fallback(self, failed_tier: str) -> Optional[TierDecision]:
        """Get the next tier in the fallback chain after a failure.

        Args:
            failed_tier: The tier that failed ("T1", "T2", or "T3")

        Returns:
            TierDecision for the next tier, or None if no fallback available
        """
        try:
            idx = _TIER_ORDER.index(failed_tier)
        except ValueError:
            logger.warning("Unknown tier: %s", failed_tier)
            return None

        # Try subsequent tiers in order
        for next_tier in _TIER_ORDER[idx + 1 :]:
            enabled = {
                "T1": self._t1_enabled,
                "T2": self._t2_enabled,
                "T3": self._t3_enabled,
            }[next_tier]
            if enabled:
                return TierDecision(
                    tier=next_tier,
                    engine_name=_TIER_META[next_tier]["engine_name"],
                    reason=f"Fallback from {failed_tier} to {next_tier}",
                    fallback_chain=self._build_fallback_chain(next_tier),
                )

        return None

    # ── Private Helpers ───────────────────────────────────────────────────

    def _build_reason(
        self, tier: str, portal_type: str, is_known: bool, url: str
    ) -> str:
        """Build human-readable reason for the routing decision."""
        if tier == "T1":
            return f"Known ATS '{portal_type}' detected → T1 FastPath"
        elif tier == "T2":
            if is_known and not self._t1_enabled:
                return (
                    f"Known ATS '{portal_type}' but T1 disabled → "
                    f"T2 BrowserUse"
                )
            return f"Unknown portal at {url} → T2 BrowserUse"
        else:  # T3
            return (
                f"T1/T2 unavailable or disabled → T3 WebSurfer fallback"
            )

    def _build_fallback_chain(self, tier: str) -> list[str]:
        """Build ordered fallback chain for a given tier."""
        try:
            idx = _TIER_ORDER.index(tier)
        except ValueError:
            return []

        # Remaining tiers after this one, filtered by enabled
        remaining = []
        enabled_map = {
            "T1": self._t1_enabled,
            "T2": self._t2_enabled,
            "T3": self._t3_enabled,
        }
        for t in _TIER_ORDER[idx + 1 :]:
            if enabled_map[t]:
                remaining.append(t)
        return remaining
