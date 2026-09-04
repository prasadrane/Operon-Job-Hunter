"""Healing Orchestrator — coordinates specialized healers across pipeline stages.

Reads unresolved errors from the persistent error DB, groups by source,
dispatches to the matching stage healer, collects results, marks resolved,
and broadcasts to SSE.
"""

from collections import defaultdict
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Type

from .base import BaseHealer, HealingReport, HealingResult

logger = logging.getLogger(__name__)


class HealingOrchestrator:
    """Coordinates specialized healers across all pipeline stages.

    Flow:
    1. Pull unresolved errors from ErrorLogRepository
    2. Group by source → dispatch to matching stage healer
    3. Each healer runs its strategies independently
    4. Collect results → mark resolved → broadcast to SSE
    """

    def __init__(
        self,
        healers: Optional[List[BaseHealer]] = None,
        dry_run: bool = False,
        since_hours: float = 168.0,  # 7 days
    ):
        self.dry_run = dry_run
        self.since_hours = since_hours
        self._healers = {h.name: h for h in (healers or [])}
        self._source_map = {h.source: h for h in (healers or [])}

    @property
    def healer_names(self) -> List[str]:
        return list(self._healers.keys())

    def get_healer(self, name: str) -> Optional[BaseHealer]:
        return self._healers.get(name)

    def run_cycle(self, stage: Optional[str] = None) -> Dict[str, HealingReport]:
        """Execute one healing cycle across all (or one) stage(s).

        Args:
            stage: If provided, only run this healer. Otherwise run all.

        Returns:
            Dict mapping healer name → HealingReport
        """
        reports: Dict[str, HealingReport] = {}

        # Pull unresolved errors from persistent DB
        try:
            from src.core.db.error_log import ErrorLogRepository
            repo = ErrorLogRepository()
            all_errors = repo.get_unresolved_errors(since_hours=self.since_hours, limit=500)
        except Exception as exc:
            logger.error("[HealingOrchestrator] Failed to read error DB: %s", exc)
            return reports

        # Group errors by source
        by_source = defaultdict(list)
        for err in all_errors:
            by_source[err.source].append(err)

        # Determine which healers to run
        if stage:
            healers_to_run = {stage: self._healers[stage]} if stage in self._healers else {}
        else:
            healers_to_run = self._healers

        # Dispatch to each healer
        for healer_name, healer in healers_to_run.items():
            if not healer.should_run():
                logger.debug("[HealingOrchestrator] Skipping %s (cooldown)", healer_name)
                continue

            source = healer.source
            errors = by_source.get(source, [])
            if not errors:
                continue

            logger.info(
                "[HealingOrchestrator] Running %s on %d errors",
                healer_name, len(errors),
            )

            try:
                report = healer.run_cycle(errors)

                # Mark resolved errors if not dry-run
                if not self.dry_run and report.fixes_applied > 0:
                    self._mark_resolved(repo, report)

                # Broadcast summary
                if report.fixes_applied > 0:
                    healer._broadcast(
                        f"Healing cycle complete: {report.fixes_applied}/{report.fixes_attempted} fixes applied",
                        level="INFO",
                    )

                reports[healer_name] = report

            except Exception as exc:
                logger.error("[HealingOrchestrator] %s failed: %s", healer_name, exc)
                healer._broadcast(f"Healing cycle failed: {exc}", level="ERROR")
                reports[healer_name] = HealingReport(
                    healer=healer_name,
                    errors_detected=len(errors),
                )

        return reports

    def run_single(self, healer_name: str) -> Optional[HealingReport]:
        """Run a single healer by name."""
        return self.run_cycle(stage=healer_name).get(healer_name)

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator and healer status."""
        try:
            from src.core.db.error_log import ErrorLogRepository
            repo = ErrorLogRepository()
            error_stats = repo.get_error_stats()
        except Exception:
            error_stats = {}

        healer_status = {}
        for name, healer in self._healers.items():
            healer_status[name] = {
                "stage_label": healer.stage_label,
                "source": healer.source,
                "cooldown_hours": healer.cooldown_hours,
                "can_run": healer.should_run(),
            }

        return {
            "error_stats": error_stats,
            "healers": healer_status,
            "dry_run": self.dry_run,
            "since_hours": self.since_hours,
        }

    def _mark_resolved(self, repo: Any, report: HealingReport) -> None:
        """Mark errors as resolved after successful healing."""
        try:
            for result in report.results:
                if result.success and result.error_id:
                    repo.mark_resolved(result.error_id)
                elif result.success and result.company:
                    # Extract portal_type from details to scope the resolution
                    portal_type = None
                    try:
                        portal_type = result.details["from"]["portal_type"]
                    except (KeyError, TypeError, AttributeError):
                        pass
                    repo.mark_company_resolved(result.company, portal_type=portal_type)
        except Exception as exc:
            logger.warning("[HealingOrchestrator] Failed to mark resolved: %s", exc)


def build_default_orchestrator(dry_run: bool = False, since_hours: float = 168.0) -> HealingOrchestrator:
    """Build an orchestrator with all default healers.

    Uses lazy imports to avoid circular dependencies at module load time.
    """
    from .discovery_healer import DiscoveryHealer
    from .gateway_healer import GatewayHealer
    from .evaluation_healer import EvaluationHealer
    from .tailoring_healer import TailoringHealer
    from .submission_healer import SubmissionHealer
    from .lifecycle_healer import LifecycleHealer

    healers = [
        DiscoveryHealer(dry_run=dry_run),
        GatewayHealer(dry_run=dry_run),
        EvaluationHealer(dry_run=dry_run),
        TailoringHealer(dry_run=dry_run),
        SubmissionHealer(dry_run=dry_run),
        LifecycleHealer(dry_run=dry_run),
    ]

    return HealingOrchestrator(healers=healers, dry_run=dry_run, since_hours=since_hours)
