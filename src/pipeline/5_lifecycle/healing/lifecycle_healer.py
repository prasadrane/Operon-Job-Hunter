"""Lifecycle Healer — handles telemetry, persistence, and cursor failures.

Strategies:
- TELEMETRY_READ_ERROR: Recreate telemetry DB schema
- PERSIST_ERROR: Recreate missing directories and files
- CURSOR_ERROR: Reset gmail cursor to beginning
"""

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, List, Optional

from .base import BaseHealer, HealingResult

logger = logging.getLogger(__name__)


class LifecycleHealer(BaseHealer):
    """Handles lifecycle stage errors — telemetry, persistence, gmail cursor."""

    name = "lifecycle"
    stage_label = "Lifecycle"
    source = "lifecycle"

    def __init__(
        self,
        telemetry_db: str = "./data/telemetry.db",
        quirks_file: str = "./data/ats_quirks.json",
        cursor_file: str = "./data/gmail_cursor.json",
        **kwargs,
    ):
        super().__init__(cooldown_hours=4.0, **kwargs)
        self.telemetry_db = telemetry_db
        self.quirks_file = quirks_file
        self.cursor_file = cursor_file
        self._last_cursor_reset: Optional[float] = None

    def can_heal(self, error_type: str, component: str) -> bool:
        return error_type in ("TELEMETRY_READ_ERROR", "PERSIST_ERROR", "CURSOR_ERROR")

    def heal(self, errors: List[Any]) -> List[HealingResult]:
        results = []
        seen_types = set()

        for error in errors:
            error_type = getattr(error, "error_type", "")
            error_id = getattr(error, "id", None)

            if error_type in seen_types:
                continue
            seen_types.add(error_type)

            if error_type == "TELEMETRY_READ_ERROR":
                results.append(self._recreate_telemetry_schema(error_id))
            elif error_type == "PERSIST_ERROR":
                results.append(self._fix_persistence(error_id))
            elif error_type == "CURSOR_ERROR":
                results.append(self._reset_cursor(error_id))

            if len(results) >= self.max_heal_per_cycle:
                break

        return results

    def _recreate_telemetry_schema(self, error_id: Optional[str]) -> HealingResult:
        """Verify and recreate telemetry.db schema if needed."""
        db_path = Path(self.telemetry_db)

        if self.dry_run:
            return HealingResult(
                healer=self.name,
                action=f"DRY RUN: Would verify/recreate telemetry schema at {db_path}",
                success=True,
                config_changed=False,
            )

        try:
            # Ensure parent dir exists
            db_path.parent.mkdir(parents=True, exist_ok=True)

            conn = sqlite3.connect(str(db_path), timeout=30.0)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")

            # Create audit_spans table if missing
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_spans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    span_id TEXT,
                    event TEXT,
                    tokens INTEGER,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()

            self._broadcast("Verified/recreated telemetry DB schema")
            return HealingResult(
                healer=self.name,
                action="Verified/recreated telemetry DB schema",
                success=True,
                error_id=error_id,
                config_changed=True,
            )
        except Exception as exc:
            return HealingResult(
                healer=self.name,
                action=f"Failed to recreate telemetry schema: {exc}",
                success=False,
                error_id=error_id,
            )

    def _fix_persistence(self, error_id: Optional[str]) -> HealingResult:
        """Ensure data directories and files exist for persistence."""
        dirs_to_check = [
            Path("./data"),
            Path("./data/artifacts"),
        ]
        files_to_check = [
            (Path(self.quirks_file), "{}"),
        ]

        created = []

        for d in dirs_to_check:
            if not d.exists():
                if self.dry_run:
                    created.append(f"dir:{d}")
                else:
                    try:
                        d.mkdir(parents=True, exist_ok=True)
                        created.append(f"dir:{d}")
                    except Exception as exc:
                        logger.warning("[LifecycleHealer] Failed to create %s: %s", d, exc)

        for f, default_content in files_to_check:
            if not f.exists():
                if self.dry_run:
                    created.append(f"file:{f}")
                else:
                    try:
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_text(default_content)
                        created.append(f"file:{f}")
                    except Exception as exc:
                        logger.warning("[LifecycleHealer] Failed to create %s: %s", f, exc)

        if created:
            action = f"Created {len(created)} missing dirs/files: {', '.join(created[:5])}"
            if not self.dry_run:
                self._broadcast(action)
            return HealingResult(
                healer=self.name,
                action=action,
                success=True,
                error_id=error_id,
                config_changed=not self.dry_run,
                details={"created": created},
            )

        return HealingResult(
            healer=self.name,
            action="All persistence dirs/files exist",
            success=True,
        )

    def _reset_cursor(self, error_id: Optional[str]) -> HealingResult:
        """Reset gmail history cursor to start from beginning."""
        cursor_path = Path(self.cursor_file)

        if self.dry_run:
            return HealingResult(
                healer=self.name,
                action=f"DRY RUN: Would reset gmail cursor at {cursor_path}",
                success=True,
                config_changed=False,
            )

        try:
            # Cooldown gate: prevent repeated cursor resets within cooldown_hours
            now = time.time()
            cooldown_seconds = self.cooldown_hours * 3600
            if (
                self._last_cursor_reset is not None
                and (now - self._last_cursor_reset) < cooldown_seconds
            ):
                return HealingResult(
                    healer=self.name,
                    action="Cursor reset skipped (cooldown)",
                    success=False,
                    error_id=error_id,
                    config_changed=False,
                )

            # Delete cursor file to force reset
            if cursor_path.exists():
                cursor_path.unlink()

            self._last_cursor_reset = now
            self._broadcast("Reset gmail cursor — will start from beginning on next sync")
            return HealingResult(
                healer=self.name,
                action="Reset gmail cursor — will restart from beginning",
                success=True,
                error_id=error_id,
                config_changed=True,
            )
        except Exception as exc:
            return HealingResult(
                healer=self.name,
                action=f"Failed to reset cursor: {exc}",
                success=False,
                error_id=error_id,
            )
