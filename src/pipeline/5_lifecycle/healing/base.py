"""Base classes for stage-specific healing agents.

Each pipeline stage has a dedicated healer that handles its error types,
owns its healing strategies, and modifies its own config/state.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import logging
import time
from typing import Any, ClassVar, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HealingResult:
    """Result from a single healing action."""

    healer: str                              # "discovery", "gateway", etc.
    action: str                              # human-readable description
    success: bool
    company: Optional[str] = None
    error_id: Optional[str] = None
    config_changed: bool = False
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "healer": self.healer,
            "action": self.action,
            "success": self.success,
            "company": self.company,
            "error_id": self.error_id,
            "config_changed": self.config_changed,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class HealingReport:
    """Report from a healer's cycle."""

    healer: str
    cycle_id: str = ""
    timestamp: str = ""
    errors_detected: int = 0
    fixes_attempted: int = 0
    fixes_applied: int = 0
    results: List[HealingResult] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
        if not self.cycle_id:
            self.cycle_id = f"{self.healer}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "healer": self.healer,
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "errors_detected": self.errors_detected,
            "fixes_attempted": self.fixes_attempted,
            "fixes_applied": self.fixes_applied,
            "results": [r.to_dict() for r in self.results],
        }


class BaseHealer(ABC):
    """Abstract base for stage-specific healing agents.

    Each healer:
    - Handles errors from one pipeline stage (identified by `source`)
    - Has its own cooldown to prevent heal-storms
    - Implements stage-specific healing strategies
    - Modifies only its own config/state
    """

    name: ClassVar[str] = ""                 # "discovery", "gateway", etc.
    stage_label: ClassVar[str] = ""          # "Discovery/Crawler", "Gateway/LLM", etc.
    source: ClassVar[str] = ""               # matches ErrorEvent.source

    def __init__(
        self,
        cooldown_hours: float = 24.0,
        max_heal_per_cycle: int = 10,
        dry_run: bool = False,
    ):
        self.cooldown_hours = cooldown_hours
        self.max_heal_per_cycle = max_heal_per_cycle
        self.dry_run = dry_run
        self._last_run: float = 0.0

    def should_run(self) -> bool:
        """Check if cooldown has elapsed since last run."""
        now = time.time()
        if now - self._last_run < (self.cooldown_hours * 3600):
            return False
        return True

    def mark_run(self) -> None:
        """Record that a healing cycle just ran."""
        self._last_run = time.time()

    @abstractmethod
    def can_heal(self, error_type: str, component: str) -> bool:
        """Whether this healer handles the given error type."""

    @abstractmethod
    def heal(self, errors: List[Any]) -> List[HealingResult]:
        """Attempt to heal a batch of errors. Returns results."""

    def run_cycle(self, errors: List[Any]) -> HealingReport:
        """Execute one healing cycle."""
        report = HealingReport(
            healer=self.name,
            errors_detected=len(errors),
        )

        if not errors:
            return report

        # Filter to errors this healer can handle
        actionable = [
            e for e in errors
            if self.can_heal(
                getattr(e, "error_type", ""),
                getattr(e, "component", ""),
            )
        ]

        if not actionable:
            return report

        # Limit per cycle
        actionable = actionable[:self.max_heal_per_cycle]
        report.fixes_attempted = len(actionable)

        # Run healing strategies
        results = self.heal(actionable)
        report.results = results
        report.fixes_applied = sum(1 for r in results if r.success)

        self.mark_run()
        return report

    def _broadcast(self, message: str, level: str = "INFO") -> None:
        """Broadcast healing action to SSE stream via AGENT_LOGS."""
        try:
            from src.interface.api.subagent_state import log_agent_event
            log_agent_event(f"[{self.stage_label} Healer] {message}", level=level)
        except Exception:
            pass
