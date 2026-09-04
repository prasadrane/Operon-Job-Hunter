"""Submission audit logging for observability and lifecycle learning.

Provides:
- AuditEntry: structured data model for each browser action
- SubmissionAuditor: SQLite persistence for submission_audit_log table
- log_audit(): dual-write function that persists to DB AND broadcasts to AGENT_LOGS

Tracks every major browser action (navigate, fill, upload, click, submit, confirm)
to enable debugging submission failures and improving the lifecycle stage.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "./data/careergraph.db"


# ─── Data Model ──────────────────────────────────────────────────────────────


@dataclass
class AuditEntry:
    """Structured representation of a browser action during submission."""

    submission_id: str                       # UUID grouping all actions for one submission
    action_type: str                         # "navigate", "fill_field", "upload_file", "click", "captcha_detect", "submit", "confirm_extract"
    target: str                              # CSS selector, URL, or field name
    success: bool                            # whether action succeeded
    id: str = ""                             # UUID, auto-generated
    job_id: Optional[str] = None             # job posting ID
    company: Optional[str] = None            # company name
    portal_type: Optional[str] = None        # "greenhouse", "lever", "ashby", "workday", etc.
    tier: Optional[str] = None               # "T1", "T2", "T3"
    step_index: Optional[int] = None         # sequential step number within submission
    duration_ms: Optional[float] = None      # action duration in milliseconds
    error_detail: Optional[str] = None       # error message if failed
    metadata: Dict[str, Any] = field(default_factory=dict)  # extra context (field value, screenshot path, etc.)
    timestamp: str = ""                      # ISO format, auto-generated

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "action_type": self.action_type,
            "target": self.target,
            "success": self.success,
            "job_id": self.job_id,
            "company": self.company,
            "portal_type": self.portal_type,
            "tier": self.tier,
            "step_index": self.step_index,
            "duration_ms": self.duration_ms,
            "error_detail": self.error_detail,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


# ─── Repository ──────────────────────────────────────────────────────────────


class SubmissionAuditor:
    """SQLite persistence for submission audit log."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create submission_audit_log table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS submission_audit_log (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    target TEXT,
                    success INTEGER NOT NULL,
                    job_id TEXT,
                    company TEXT,
                    portal_type TEXT,
                    tier TEXT,
                    step_index INTEGER,
                    duration_ms REAL,
                    error_detail TEXT,
                    metadata TEXT,
                    timestamp TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_submission_id ON submission_audit_log(submission_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_job_id ON submission_audit_log(job_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_company ON submission_audit_log(company)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON submission_audit_log(timestamp)")
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for SQLite connections."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def log_entry(self, entry: AuditEntry) -> AuditEntry:
        """Persist an audit entry to the database."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO submission_audit_log
                   (id, submission_id, action_type, target, success, job_id, company,
                    portal_type, tier, step_index, duration_ms, error_detail, metadata, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.id,
                    entry.submission_id,
                    entry.action_type,
                    entry.target,
                    1 if entry.success else 0,
                    entry.job_id,
                    entry.company,
                    entry.portal_type,
                    entry.tier,
                    entry.step_index,
                    entry.duration_ms,
                    entry.error_detail,
                    json.dumps(entry.metadata) if entry.metadata else None,
                    entry.timestamp,
                ),
            )
        return entry

    def get_entries_by_submission(self, submission_id: str) -> List[AuditEntry]:
        """Get all audit entries for a submission, ordered by step_index or timestamp."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM submission_audit_log WHERE submission_id = ? ORDER BY step_index, timestamp",
                (submission_id,),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_entries_by_job(self, job_id: str, limit: int = 100) -> List[AuditEntry]:
        """Get audit entries for a specific job."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM submission_audit_log WHERE job_id = ? ORDER BY timestamp DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_failed_actions(self, since_hours: float = 24.0, limit: int = 100) -> List[AuditEntry]:
        """Get failed actions from the last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=since_hours)
        cutoff_iso = cutoff.isoformat()

        with self.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM submission_audit_log
                   WHERE success = 0 AND timestamp >= ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (cutoff_iso, limit),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate audit statistics."""
        with self.connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM submission_audit_log").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM submission_audit_log WHERE success = 0").fetchone()[0]
            by_action = conn.execute(
                "SELECT action_type, COUNT(*) as cnt FROM submission_audit_log GROUP BY action_type ORDER BY cnt DESC"
            ).fetchall()
            by_tier = conn.execute(
                "SELECT tier, COUNT(*) as cnt FROM submission_audit_log WHERE tier IS NOT NULL GROUP BY tier ORDER BY cnt DESC"
            ).fetchall()
            avg_duration = conn.execute(
                "SELECT action_type, AVG(duration_ms) as avg_ms FROM submission_audit_log WHERE duration_ms IS NOT NULL GROUP BY action_type"
            ).fetchall()

        return {
            "total": total,
            "failed": failed,
            "success_rate": (total - failed) / total if total > 0 else 0.0,
            "by_action": {row[0]: row[1] for row in by_action},
            "by_tier": {row[0]: row[1] for row in by_tier if row[0]},
            "avg_duration_ms": {row[0]: row[1] for row in avg_duration},
        }

    def cleanup_old_entries(self, days: int = 30) -> int:
        """Remove audit entries older than N days. Returns count deleted."""
        cutoff_iso = (datetime.utcnow() - timedelta(days=days)).isoformat()
        with self.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM submission_audit_log WHERE timestamp < ?",
                (cutoff_iso,),
            )
            return cursor.rowcount

    def _row_to_entry(self, row: sqlite3.Row) -> AuditEntry:
        """Convert a database row to an AuditEntry."""
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except Exception:
                pass
        return AuditEntry(
            id=row["id"],
            submission_id=row["submission_id"],
            action_type=row["action_type"],
            target=row["target"] or "",
            success=bool(row["success"]),
            job_id=row["job_id"],
            company=row["company"],
            portal_type=row["portal_type"],
            tier=row["tier"],
            step_index=row["step_index"],
            duration_ms=row["duration_ms"],
            error_detail=row["error_detail"],
            metadata=metadata,
            timestamp=row["timestamp"],
        )


# ─── Public API ──────────────────────────────────────────────────────────────

# Module-level singleton to avoid repeated table creation
_auditor: Optional[SubmissionAuditor] = None


def _get_auditor() -> SubmissionAuditor:
    """Get or create the module-level auditor singleton."""
    global _auditor
    if _auditor is None:
        _auditor = SubmissionAuditor()
    return _auditor


def log_audit(
    submission_id: str,
    action_type: str,
    target: str,
    success: bool,
    job_id: Optional[str] = None,
    company: Optional[str] = None,
    portal_type: Optional[str] = None,
    tier: Optional[str] = None,
    step_index: Optional[int] = None,
    duration_ms: Optional[float] = None,
    error_detail: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> AuditEntry:
    """Log a submission audit entry to both SQLite and AGENT_LOGS.

    This is the primary entry point for audit logging throughout the submission pipeline.
    It dual-writes to:
    1. SQLite submission_audit_log table (persistent, survives restarts)
    2. AGENT_LOGS in-memory buffer (SSE broadcast for UI)

    Args:
        submission_id: UUID grouping all actions for one submission
        action_type: Browser action — "navigate", "fill_field", "upload_file", "click",
                     "captcha_detect", "submit", "confirm_extract"
        target: CSS selector, URL, or field name
        success: whether action succeeded
        job_id: job posting ID
        company: company name
        portal_type: ATS portal type
        tier: "T1", "T2", "T3"
        step_index: sequential step number within submission
        duration_ms: action duration in milliseconds
        error_detail: error message if failed
        metadata: additional context dict
        db_path: override DB path (for testing)

    Returns:
        The created AuditEntry
    """
    entry = AuditEntry(
        submission_id=submission_id,
        action_type=action_type,
        target=target,
        success=success,
        job_id=job_id,
        company=company,
        portal_type=portal_type,
        tier=tier,
        step_index=step_index,
        duration_ms=duration_ms,
        error_detail=error_detail,
        metadata=metadata or {},
    )

    # 1. Persist to SQLite
    try:
        auditor = SubmissionAuditor(db_path) if db_path else _get_auditor()
        auditor.log_entry(entry)
    except Exception as exc:
        logger.warning("Failed to persist audit entry to SQLite: %s", exc)

    # 2. Broadcast to AGENT_LOGS for SSE visibility
    try:
        from src.interface.api.subagent_state import log_agent_event
        status = "OK" if success else "FAIL"
        log_agent_event(
            f"SUBMIT_AUDIT|{company or 'unknown'}|{portal_type or 'unknown'}|{tier or 'unknown'}|{action_type}|{status}|{target}",
            level="INFO" if success else "WARN",
        )
    except Exception:
        pass  # subagent_state may not be available in all contexts

    return entry
