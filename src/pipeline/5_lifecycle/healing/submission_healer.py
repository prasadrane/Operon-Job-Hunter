"""Submission Healer — handles browser, captcha, and submission failures.

Strategies:
- BROWSER_ACTION_ERROR: Clear stale browser locks, reset Playwright state
- CAPTCHA_TIMEOUT: Log pattern (no auto-fix available without service config)
- SUBMISSION_ERROR: Attempt browser profile cleanup
"""

import logging
import shutil
from pathlib import Path
from typing import Any, List, Optional

from .base import BaseHealer, HealingResult

logger = logging.getLogger(__name__)

# Known stale lock file patterns in browser profiles
STALE_LOCK_PATTERNS = [
    "SingletonLock",
    "SingletonSocket",
    "SingletonCookie",
    "lockfile",
]


class SubmissionHealer(BaseHealer):
    """Handles submission stage errors — browser failures, captcha timeouts, submission errors."""

    name = "submission"
    stage_label = "Submission"
    source = "submission"

    def __init__(self, browser_profile_dir: str = "./data/browser_profile", **kwargs):
        super().__init__(cooldown_hours=2.0, **kwargs)  # 2h cooldown
        self.browser_profile_dir = browser_profile_dir

    def can_heal(self, error_type: str, component: str) -> bool:
        return error_type in ("BROWSER_ACTION_ERROR", "CAPTCHA_TIMEOUT", "SUBMISSION_ERROR")

    def heal(self, errors: List[Any]) -> List[HealingResult]:
        results = []
        has_browser_error = False
        has_captcha_timeout = False
        has_submission_error = False
        error_ids = []

        for error in errors:
            error_type = getattr(error, "error_type", "")
            error_id = getattr(error, "id", None)
            error_ids.append(error_id)

            if error_type == "BROWSER_ACTION_ERROR":
                has_browser_error = True
            elif error_type == "CAPTCHA_TIMEOUT":
                has_captcha_timeout = True
            elif error_type == "SUBMISSION_ERROR":
                has_submission_error = True

        # Browser errors: clean stale locks
        if has_browser_error:
            results.append(self._clean_browser_locks(error_ids))

        # Captcha timeouts: log pattern, suggest config change
        if has_captcha_timeout:
            results.append(HealingResult(
                healer=self.name,
                action="CAPTCHA timeout detected — consider increasing captcha timeout or switching captcha service",
                success=False,
                details={"recommendation": "Increase captcha_handler timeout from 60s to 120s in config"},
            ))

        # Submission errors: attempt profile cleanup
        if has_submission_error and not has_browser_error:
            results.append(self._cleanup_browser_profile(error_ids))

        return results[:self.max_heal_per_cycle]

    def _clean_browser_locks(self, error_ids: List[Optional[str]]) -> HealingResult:
        """Remove stale lock files from browser profile directory."""
        profile_path = Path(self.browser_profile_dir)
        if not profile_path.exists():
            return HealingResult(
                healer=self.name,
                action="Browser profile directory does not exist — will be created on next launch",
                success=True,
            )

        cleaned = []
        for lock_name in STALE_LOCK_PATTERNS:
            for lock_file in profile_path.rglob(lock_name):
                if self.dry_run:
                    cleaned.append(str(lock_file))
                else:
                    try:
                        lock_file.unlink()
                        cleaned.append(str(lock_file))
                    except Exception as exc:
                        logger.warning("[SubmissionHealer] Failed to remove %s: %s", lock_file, exc)

        if cleaned:
            action = f"Cleaned {len(cleaned)} stale lock files from browser profile"
            if not self.dry_run:
                self._broadcast(action)
            return HealingResult(
                healer=self.name,
                action=action,
                success=True,
                error_id=error_ids[0] if error_ids else None,
                config_changed=not self.dry_run,
                details={"cleaned_files": cleaned},
            )

        return HealingResult(
            healer=self.name,
            action="No stale lock files found in browser profile",
            success=True,
        )

    def _cleanup_browser_profile(self, error_ids: List[Optional[str]]) -> HealingResult:
        """Full browser profile cleanup — remove Default cache dirs."""
        profile_path = Path(self.browser_profile_dir)
        if not profile_path.exists():
            return HealingResult(
                healer=self.name,
                action="Browser profile does not exist — nothing to clean",
                success=True,
            )

        cache_dirs = [
            profile_path / "Default" / "Cache",
            profile_path / "Default" / "Code Cache",
            profile_path / "Default" / "GPUCache",
        ]

        cleaned = []
        for cache_dir in cache_dirs:
            if cache_dir.exists():
                if self.dry_run:
                    cleaned.append(str(cache_dir))
                else:
                    try:
                        shutil.rmtree(str(cache_dir))
                        cleaned.append(str(cache_dir))
                    except Exception as exc:
                        logger.warning("[SubmissionHealer] Failed to remove %s: %s", cache_dir, exc)

        if cleaned:
            action = f"Cleaned {len(cleaned)} browser cache directories"
            if not self.dry_run:
                self._broadcast(action)
            return HealingResult(
                healer=self.name,
                action=action,
                success=True,
                error_id=error_ids[0] if error_ids else None,
                config_changed=not self.dry_run,
                details={"cleaned_dirs": cleaned},
            )

        return HealingResult(
            healer=self.name,
            action="No cache directories to clean",
            success=True,
        )
