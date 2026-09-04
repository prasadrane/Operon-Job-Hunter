"""Persistent structured error logging for self-healing agent data source.

Provides:
- ErrorEvent: structured data model for pipeline errors
- ErrorLogRepository: SQLite persistence for crawler_errors table
- log_error(): dual-write function that persists to DB AND broadcasts to AGENT_LOGS
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
class ErrorEvent:
    """Structured representation of a pipeline error."""

    source: str                              # "crawler", "state_machine", "gateway", "submission", "evaluation", "tailoring", "lifecycle", "batch"
    component: str                           # e.g. "greenhouse_crawler", "node_discover", "alibaba_provider"
    error_type: str                          # "HTTP_404", "HTTP_422", "TIMEOUT", "RATE_LIMIT", "PARSE_ERROR", "CIRCUIT_BREAKER", "FATAL"
    message: str                             # human-readable error description
    id: str = ""                             # UUID, auto-generated
    company: Optional[str] = None            # company name if applicable
    portal_type: Optional[str] = None        # "greenhouse", "lever", "ashby", "workday", etc.
    board_token: Optional[str] = None        # board identifier
    http_status: Optional[int] = None        # HTTP status code if applicable
    metadata: Dict[str, Any] = field(default_factory=dict)  # extra context
    timestamp: str = ""                      # ISO format, auto-generated
    resolved: bool = False                   # has self-healing fixed this?

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "component": self.component,
            "company": self.company,
            "portal_type": self.portal_type,
            "board_token": self.board_token,
            "error_type": self.error_type,
            "http_status": self.http_status,
            "message": self.message,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
        }


# ─── Repository ──────────────────────────────────────────────────────────────


class ErrorLogRepository:
    """SQLite persistence for structured error events."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create crawler_errors table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crawler_errors (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    component TEXT NOT NULL,
                    company TEXT,
                    portal_type TEXT,
                    board_token TEXT,
                    error_type TEXT NOT NULL,
                    http_status INTEGER,
                    message TEXT,
                    metadata TEXT,
                    timestamp TEXT NOT NULL,
                    resolved INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_crawler_errors_company ON crawler_errors(company)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_crawler_errors_unresolved ON crawler_errors(resolved, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_crawler_errors_source ON crawler_errors(source)")
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

    def log_error(self, event: ErrorEvent) -> ErrorEvent:
        """Persist an error event to the database."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO crawler_errors
                   (id, source, component, company, portal_type, board_token,
                    error_type, http_status, message, metadata, timestamp, resolved)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.source,
                    event.component,
                    event.company,
                    event.portal_type,
                    event.board_token,
                    event.error_type,
                    event.http_status,
                    event.message,
                    json.dumps(event.metadata) if event.metadata else None,
                    event.timestamp,
                    1 if event.resolved else 0,
                ),
            )
        return event

    def get_recent_errors(self, limit: int = 50, source: Optional[str] = None) -> List[ErrorEvent]:
        """Get recent error events, optionally filtered by source."""
        with self.connection() as conn:
            if source:
                rows = conn.execute(
                    "SELECT * FROM crawler_errors WHERE source = ? ORDER BY timestamp DESC LIMIT ?",
                    (source, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM crawler_errors ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_unresolved_errors(self, since_hours: float = 24.0, limit: int = 100) -> List[ErrorEvent]:
        """Get unresolved errors from the last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=since_hours)
        cutoff_iso = cutoff.isoformat()

        with self.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM crawler_errors
                   WHERE resolved = 0 AND timestamp >= ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (cutoff_iso, limit),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_errors_by_company(self, company: str, limit: int = 50) -> List[ErrorEvent]:
        """Get errors for a specific company."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM crawler_errors WHERE company = ? ORDER BY timestamp DESC LIMIT ?",
                (company, limit),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def mark_resolved(self, error_id: str) -> bool:
        """Mark an error as resolved. Returns True if found and updated."""
        with self.connection() as conn:
            cursor = conn.execute(
                "UPDATE crawler_errors SET resolved = 1 WHERE id = ?",
                (error_id,),
            )
            return cursor.rowcount > 0

    def mark_company_resolved(self, company: str, portal_type: Optional[str] = None) -> int:
        """Mark all unresolved errors for a company (and optional portal_type) as resolved.
        Returns count of updated rows."""
        with self.connection() as conn:
            if portal_type:
                cursor = conn.execute(
                    "UPDATE crawler_errors SET resolved = 1 WHERE company = ? AND portal_type = ? AND resolved = 0",
                    (company, portal_type),
                )
            else:
                cursor = conn.execute(
                    "UPDATE crawler_errors SET resolved = 1 WHERE company = ? AND resolved = 0",
                    (company,),
                )
            return cursor.rowcount

    def get_error_stats(self) -> Dict[str, Any]:
        """Get aggregate error statistics."""
        with self.connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM crawler_errors").fetchone()[0]
            unresolved = conn.execute("SELECT COUNT(*) FROM crawler_errors WHERE resolved = 0").fetchone()[0]
            by_source = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM crawler_errors GROUP BY source ORDER BY cnt DESC"
            ).fetchall()
            by_type = conn.execute(
                "SELECT error_type, COUNT(*) as cnt FROM crawler_errors GROUP BY error_type ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            by_company = conn.execute(
                """SELECT company, COUNT(*) as cnt FROM crawler_errors
                   WHERE company IS NOT NULL AND resolved = 0
                   GROUP BY company ORDER BY cnt DESC LIMIT 20"""
            ).fetchall()

        return {
            "total": total,
            "unresolved": unresolved,
            "resolved": total - unresolved,
            "by_source": {row[0]: row[1] for row in by_source},
            "by_type": {row[0]: row[1] for row in by_type},
            "top_companies": {row[0]: row[1] for row in by_company if row[0]},
        }

    def cleanup_old_errors(self, days: int = 30) -> int:
        """Remove errors older than N days. Returns count deleted."""
        cutoff_iso = (datetime.utcnow() - timedelta(days=days)).isoformat()
        with self.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM crawler_errors WHERE timestamp < ? AND resolved = 1",
                (cutoff_iso,),
            )
            return cursor.rowcount

    def _row_to_event(self, row: sqlite3.Row) -> ErrorEvent:
        """Convert a database row to an ErrorEvent."""
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except Exception:
                pass
        return ErrorEvent(
            id=row["id"],
            source=row["source"],
            component=row["component"],
            company=row["company"],
            portal_type=row["portal_type"],
            board_token=row["board_token"],
            error_type=row["error_type"],
            http_status=row["http_status"],
            message=row["message"] or "",
            metadata=metadata,
            timestamp=row["timestamp"],
            resolved=bool(row["resolved"]),
        )


# ─── Public API ──────────────────────────────────────────────────────────────

# Module-level singleton to avoid repeated table creation
_repo: Optional[ErrorLogRepository] = None


def _get_repo() -> ErrorLogRepository:
    """Get or create the module-level repository singleton."""
    global _repo
    if _repo is None:
        _repo = ErrorLogRepository()
    return _repo


def log_error(
    source: str,
    component: str,
    error_type: str,
    message: str,
    company: Optional[str] = None,
    portal_type: Optional[str] = None,
    board_token: Optional[str] = None,
    http_status: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> ErrorEvent:
    """Log a structured error event to both SQLite and AGENT_LOGS.

    This is the primary entry point for error logging throughout the codebase.
    It dual-writes to:
    1. SQLite crawler_errors table (persistent, survives restarts)
    2. AGENT_LOGS in-memory buffer (SSE broadcast for UI)

    Args:
        source: Pipeline stage — "crawler", "state_machine", "gateway", "submission",
                "evaluation", "tailoring", "lifecycle", "batch"
        component: Specific component — e.g. "greenhouse_crawler", "node_discover"
        error_type: Error classification — "HTTP_404", "HTTP_422", "TIMEOUT",
                    "RATE_LIMIT", "PARSE_ERROR", "CIRCUIT_BREAKER", "FATAL"
        message: Human-readable error description
        company: Company name if applicable
        portal_type: ATS portal type if applicable
        board_token: Board identifier if applicable
        http_status: HTTP status code if applicable
        metadata: Additional context dict
        db_path: Override DB path (for testing)

    Returns:
        The created ErrorEvent
    """
    event = ErrorEvent(
        source=source,
        component=component,
        error_type=error_type,
        message=message,
        company=company,
        portal_type=portal_type,
        board_token=board_token,
        http_status=http_status,
        metadata=metadata or {},
    )

    # 1. Persist to SQLite
    try:
        repo = ErrorLogRepository(db_path) if db_path else _get_repo()
        repo.log_error(event)
    except Exception as exc:
        logger.warning("Failed to persist error to SQLite: %s", exc)

    # 2. Broadcast to AGENT_LOGS for SSE visibility
    try:
        from src.interface.api.subagent_state import log_agent_event
        company_label = company or component
        log_agent_event(
            f"CRAWLER_ERROR|{company_label}|{portal_type or 'unknown'}|{board_token or 'unknown'}|{error_type}: {message}",
            level="ERROR",
        )
    except Exception:
        pass  # subagent_state may not be available in all contexts

    return event
