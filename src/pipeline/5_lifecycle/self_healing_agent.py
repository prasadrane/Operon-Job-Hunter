"""Self-Healing Agent: Detects crawler failures from live logs and auto-fixes company configurations.

Runs on a scheduled interval, reads AGENT_LOGS for CRAWLER_ERROR patterns,
attempts automated fixes (try alternative portal types/tokens), validates
the fix, and updates companies.yaml.
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .healing_strategies import (
    CrawlerError,
    HealingResult,
    attempt_healing,
)

logger = logging.getLogger(__name__)


# ─── Data Models ─────────────────────────────────────────────────────────────


@dataclass
class HealingAction:
    """A proposed fix with original and new config."""

    company_name: str
    original_config: Dict[str, Any]
    proposed_config: Dict[str, Any]
    healing_result: HealingResult


@dataclass
class HealingReport:
    """Report from a healing cycle."""

    cycle_id: str
    timestamp: str = ""
    errors_detected: int = 0
    fixes_attempted: int = 0
    fixes_applied: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp or datetime.utcnow().isoformat(),
            "errors_detected": self.errors_detected,
            "fixes_attempted": self.fixes_attempted,
            "fixes_applied": self.fixes_applied,
            "details": self.details,
        }


# ─── Error Detection ─────────────────────────────────────────────────────────

# Pattern: CRAWLER_ERROR|company_name|portal_type|board_token|error_message
CRAWLER_ERROR_PATTERN = re.compile(
    r"CRAWLER_ERROR\|([^|]+)\|([^|]+)\|([^|]+)\|(.+)"
)

# Fallback patterns for parsing crawler warnings from portal_crawler.py
GREENHOUSE_FAIL_PATTERN = re.compile(
    r"Greenhouse crawl failed for board (\w+):.*?(\d{3})"
)
LEVER_FAIL_PATTERN = re.compile(
    r"Lever crawl failed for board (\w+):.*?(\d{3})"
)
ASHBY_FAIL_PATTERN = re.compile(
    r"Ashby crawl failed for board (\w+):.*?(\d{3})"
)
WORKDAY_FAIL_PATTERN = re.compile(
    r"Workday crawl failed for tenant (\w+):.*?(\d{3})"
)
SMARTRECRUITERS_FAIL_PATTERN = re.compile(
    r"SmartRecruiters crawl failed for (\w+):.*?(\d{3})"
)


def detect_errors_from_logs(agent_logs: List[Dict[str, Any]]) -> List[CrawlerError]:
    """Parse AGENT_LOGS for crawler error patterns.

    Returns a deduplicated list of CrawlerError objects.
    """
    errors: Dict[str, CrawlerError] = {}  # keyed by company_name

    for log_entry in agent_logs:
        message = log_entry.get("message", "")
        level = log_entry.get("level", "INFO")
        timestamp = log_entry.get("timestamp", "")

        # Check for structured CRAWLER_ERROR pattern
        match = CRAWLER_ERROR_PATTERN.search(message)
        if match:
            company = match.group(1).strip()
            portal = match.group(2).strip()
            token = match.group(3).strip()
            error_msg = match.group(4).strip()

            # Extract HTTP status from error message
            http_status = None
            status_match = re.search(r"(\d{3})", error_msg)
            if status_match:
                http_status = int(status_match.group(1))

            if company not in errors:
                errors[company] = CrawlerError(
                    company_name=company,
                    portal_type=portal,
                    board_token=token,
                    error_message=error_msg,
                    http_status=http_status,
                    timestamp=timestamp,
                )
            continue

        # Check for portal-specific failure patterns
        for pattern, portal_type in [
            (GREENHOUSE_FAIL_PATTERN, "greenhouse"),
            (LEVER_FAIL_PATTERN, "lever"),
            (ASHBY_FAIL_PATTERN, "ashby"),
            (WORKDAY_FAIL_PATTERN, "workday"),
            (SMARTRECRUITERS_FAIL_PATTERN, "smartrecruiters"),
        ]:
            m = pattern.search(message)
            if m:
                token = m.group(1)
                status = int(m.group(2))
                # We don't have company name from these patterns, use token as proxy
                company = token
                if company not in errors:
                    errors[company] = CrawlerError(
                        company_name=company,
                        portal_type=portal_type,
                        board_token=token,
                        error_message=message,
                        http_status=status,
                        timestamp=timestamp,
                    )
                break

    return list(errors.values())


# ─── Config Updater ──────────────────────────────────────────────────────────


def load_companies_yaml(filepath: str) -> List[Dict[str, Any]]:
    """Load companies from YAML file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = yaml.safe_load(f)
        if isinstance(content, dict):
            return content.get("companies", [])
        elif isinstance(content, list):
            return content
        return []


def save_companies_yaml(filepath: str, companies: List[Dict[str, Any]]) -> None:
    """Safely save companies to YAML file with backup.

    Creates a .bak backup before writing. Uses atomic write pattern.
    """
    path = Path(filepath)

    # Create backup
    bak_path = path.with_suffix(".yaml.bak")
    if path.exists():
        shutil.copy2(str(path), str(bak_path))

    # Write to temp file first
    dir_name = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_name), suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {"companies": companies},
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        # Verify the temp file is valid YAML
        with open(tmp_path, "r", encoding="utf-8") as f:
            yaml.safe_load(f)

        # Atomic replace
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def update_company_config(
    filepath: str,
    company_name: str,
    updates: Dict[str, Any],
) -> bool:
    """Update a company's configuration in companies.yaml.

    Returns True if the update was applied successfully.
    """
    try:
        companies = load_companies_yaml(filepath)

        for company in companies:
            if company.get("name", "").lower() == company_name.lower():
                company.update(updates)
                save_companies_yaml(filepath, companies)
                return True

        logger.warning("Company not found in %s: %s", filepath, company_name)
        return False

    except Exception as exc:
        logger.error("Failed to update company config for %s: %s", company_name, exc)
        return False


# ─── Audit Log ───────────────────────────────────────────────────────────────


class HealingAuditLog:
    """Append-only JSON audit log for healing actions."""

    def __init__(self, log_path: str = "./data/self_healing_log.json") -> None:
        self.log_path = log_path
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)

    def record(self, result: HealingResult, applied: bool = False) -> None:
        """Record a healing attempt."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "company": result.company_name,
            "original_portal": result.original_portal,
            "original_token": result.original_token,
            "new_portal": result.new_portal,
            "new_token": result.new_token,
            "success": result.success,
            "applied": applied,
            "validation_status": result.validation_status,
            "candidates_tried": result.candidates_tried,
            "error": result.error,
        }

        # Load existing entries
        entries = []
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            except Exception:
                entries = []

        entries.append(entry)

        # Keep last 500 entries
        entries = entries[-500:]

        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, default=str)

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent healing entries."""
        if not os.path.exists(self.log_path):
            return []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                entries = json.load(f)
            return entries[-limit:]
        except Exception:
            return []

    def was_healed_recently(self, company_name: str, hours: float = 24.0) -> bool:
        """Check if a company was healed within the last N hours."""
        entries = self.get_recent(limit=100)
        cutoff = datetime.utcnow().timestamp() - (hours * 3600)

        for entry in reversed(entries):
            if entry.get("company", "").lower() == company_name.lower():
                try:
                    ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
                    if ts >= cutoff:
                        return True
                except Exception:
                    pass
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get healing statistics."""
        entries = self.get_recent(limit=500)
        total = len(entries)
        successes = sum(1 for e in entries if e.get("success"))
        applied = sum(1 for e in entries if e.get("applied"))

        return {
            "total_attempts": total,
            "successes": successes,
            "applied": applied,
            "success_rate": successes / total if total > 0 else 0.0,
        }


# ─── Main Agent ──────────────────────────────────────────────────────────────


class SelfHealingAgent:
    """Scheduled agent that detects crawler failures and auto-fixes company configs."""

    def __init__(
        self,
        companies_file: Optional[str] = None,
        audit_log: Optional[HealingAuditLog] = None,
        max_heal_per_cycle: int = 5,
        cooldown_hours: float = 24.0,
        dry_run: bool = False,
    ) -> None:
        if not companies_file:
            from src.core.config import get_settings
            companies_file = str(get_settings().companies_yaml_path)
        self.companies_file = companies_file
        self.audit_log = audit_log or HealingAuditLog()
        self.max_heal_per_cycle = max_heal_per_cycle
        self.cooldown_hours = cooldown_hours
        self.dry_run = dry_run

    def _get_agent_logs(self) -> List[Dict[str, Any]]:
        """Read AGENT_LOGS from subagent_state."""
        try:
            from src.interface.api.subagent_state import AGENT_LOGS
            return list(AGENT_LOGS)
        except Exception:
            return []

    def _get_company_config(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Find a company's config from companies.yaml."""
        try:
            companies = load_companies_yaml(self.companies_file)
            for company in companies:
                if company.get("name", "").lower() == company_name.lower():
                    return company
                # Also match by board_token
                if company.get("board_token", "").lower() == company_name.lower():
                    return company
        except Exception as exc:
            logger.error("Failed to load company config: %s", exc)
        return None

    def detect_errors(self) -> List[CrawlerError]:
        """Detect crawler errors from persistent DB and live logs."""
        errors: List[CrawlerError] = []
        seen_companies = set()

        # Primary: read from persistent DB
        try:
            from src.core.db.error_log import ErrorLogRepository
            repo = ErrorLogRepository()
            db_errors = repo.get_unresolved_errors(since_hours=self.cooldown_hours, limit=100)
            for db_err in db_errors:
                company = db_err.company or db_err.component
                if company not in seen_companies:
                    seen_companies.add(company)
                    errors.append(CrawlerError(
                        company_name=company,
                        portal_type=db_err.portal_type or "unknown",
                        board_token=db_err.board_token or "",
                        error_message=db_err.message,
                        http_status=db_err.http_status,
                        careers_url=None,
                        timestamp=db_err.timestamp,
                    ))
        except Exception as exc:
            logger.warning("[SelfHeal] Failed to read from error DB: %s", exc)

        # Secondary: read from AGENT_LOGS (current session)
        logs = self._get_agent_logs()
        log_errors = detect_errors_from_logs(logs)
        for error in log_errors:
            if error.company_name not in seen_companies:
                seen_companies.add(error.company_name)
                errors.append(error)

        # Enrich errors with company config data
        for error in errors:
            config = self._get_company_config(error.company_name)
            if config:
                error.careers_url = config.get("careers_url")
                # Ensure we have the correct portal_type from config
                if not error.portal_type or error.portal_type == "unknown":
                    error.portal_type = config.get("portal_type", "greenhouse")
                    error.board_token = config.get("board_token", error.board_token)

        return errors

    def attempt_healing(self, errors: List[CrawlerError]) -> List[HealingAction]:
        """Attempt to heal each error, returning a list of validated actions."""
        actions: List[HealingAction] = []

        for error in errors:
            # Skip if recently healed
            if self.audit_log.was_healed_recently(error.company_name, self.cooldown_hours):
                logger.debug("[SelfHeal] Skipping %s — healed recently", error.company_name)
                continue

            # Get current config
            config = self._get_company_config(error.company_name)
            if not config:
                logger.warning("[SelfHeal] No config found for %s", error.company_name)
                continue

            # Attempt healing
            result = attempt_healing(error, max_candidates=10)
            self.audit_log.record(result, applied=False)

            if result.success:
                original_config = {
                    "portal_type": config.get("portal_type"),
                    "board_token": config.get("board_token"),
                }
                proposed_config = {
                    "portal_type": result.new_portal,
                    "board_token": result.new_token,
                }
                actions.append(HealingAction(
                    company_name=error.company_name,
                    original_config=original_config,
                    proposed_config=proposed_config,
                    healing_result=result,
                ))

            # Rate limit
            if len(actions) >= self.max_heal_per_cycle:
                break

        return actions

    def apply_fixes(self, actions: List[HealingAction]) -> HealingReport:
        """Apply validated fixes to companies.yaml."""
        cycle_id = f"heal_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        report = HealingReport(
            cycle_id=cycle_id,
            timestamp=datetime.utcnow().isoformat(),
            errors_detected=0,
            fixes_attempted=len(actions),
            fixes_applied=0,
        )

        for action in actions:
            if self.dry_run:
                logger.info(
                    "[SelfHeal] DRY RUN: Would update %s — %s/%s → %s/%s",
                    action.company_name,
                    action.original_config["portal_type"],
                    action.original_config["board_token"],
                    action.proposed_config["portal_type"],
                    action.proposed_config["board_token"],
                )
                report.details.append({
                    "company": action.company_name,
                    "status": "dry_run",
                    "from": action.original_config,
                    "to": action.proposed_config,
                })
                continue

            success = update_company_config(
                self.companies_file,
                action.company_name,
                action.proposed_config,
            )

            if success:
                report.fixes_applied += 1
                self.audit_log.record(action.healing_result, applied=True)

                # Mark errors as resolved in persistent DB
                try:
                    from src.core.db.error_log import ErrorLogRepository
                    repo = ErrorLogRepository()
                    portal = action.proposed_config.get("portal_type")
                    repo.mark_company_resolved(action.company_name, portal_type=action.original_config.get("portal_type"))
                except Exception:
                    pass

                # Broadcast to SSE stream
                try:
                    from src.interface.api.subagent_state import log_agent_event
                    log_agent_event(
                        f"[SelfHeal] Fixed {action.company_name}: "
                        f"{action.original_config['portal_type']}/{action.original_config['board_token']} "
                        f"→ {action.proposed_config['portal_type']}/{action.proposed_config['board_token']}"
                    )
                except Exception:
                    pass

                logger.info(
                    "[SelfHeal] Applied fix for %s: %s/%s → %s/%s",
                    action.company_name,
                    action.original_config["portal_type"],
                    action.original_config["board_token"],
                    action.proposed_config["portal_type"],
                    action.proposed_config["board_token"],
                )
            else:
                logger.warning("[SelfHeal] Failed to apply fix for %s", action.company_name)

            report.details.append({
                "company": action.company_name,
                "status": "applied" if success else "failed",
                "from": action.original_config,
                "to": action.proposed_config,
            })

        return report

    def run_cycle(self) -> HealingReport:
        """Execute one healing cycle: detect → heal → validate → update."""
        logger.info("[SelfHeal] Starting healing cycle...")

        # Detect errors
        errors = self.detect_errors()
        logger.info("[SelfHeal] Detected %d crawler errors", len(errors))

        if not errors:
            return HealingReport(
                cycle_id=f"heal_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                timestamp=datetime.utcnow().isoformat(),
                errors_detected=0,
            )

        # Attempt healing
        actions = self.attempt_healing(errors)
        logger.info("[SelfHeal] Generated %d healing actions", len(actions))

        # Apply fixes
        report = self.apply_fixes(actions)
        report.errors_detected = len(errors)

        logger.info(
            "[SelfHeal] Cycle complete: %d errors → %d fixes attempted → %d applied",
            report.errors_detected,
            report.fixes_attempted,
            report.fixes_applied,
        )

        return report
