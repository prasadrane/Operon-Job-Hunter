"""Per-submission telemetry collection for monitoring and optimization.

Tracks submission lifecycle across 3-tier architecture:
- T1: FastPath deterministic DOM autofill
- T2: ATS-specific adapters
- T3: WebSurfer Agent (LLM-driven fallback)

Collects metrics: success rates, duration, token costs, error breakdowns.
Feeds P3d observability dashboard and P5 lifecycle retrospective agent.
"""

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "./data/careergraph.db"


class SubmissionTelemetry:
    """SQLite persistence for submission telemetry and metrics aggregation."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create submission_telemetry and tier_attempts tables."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS submission_telemetry (
                    session_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    portal_type TEXT,
                    started_at TIMESTAMP,
                    ended_at TIMESTAMP,
                    success INTEGER,
                    total_duration_sec REAL,
                    tiers_attempted TEXT,
                    final_tier TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tier_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    tier TEXT,
                    started_at TIMESTAMP,
                    ended_at TIMESTAMP,
                    success INTEGER,
                    duration_sec REAL,
                    tokens_used INTEGER,
                    error_type TEXT,
                    FOREIGN KEY (session_id) REFERENCES submission_telemetry(session_id)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_telemetry_started_at ON submission_telemetry(started_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tier_session ON tier_attempts(session_id)"
            )
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

    def record_submission_start(self, job_id: str, portal_type: str) -> str:
        """Record the start of a submission attempt.

        Args:
            job_id: Job posting identifier
            portal_type: ATS portal type (greenhouse, lever, ashby, workday, etc.)

        Returns:
            session_id: UUID for this submission session
        """
        session_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat()

        with self.connection() as conn:
            conn.execute(
                """INSERT INTO submission_telemetry
                   (session_id, job_id, portal_type, started_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, job_id, portal_type, started_at),
            )

        return session_id

    def record_tier_attempt(self, session_id: str, tier: str, started_at: str) -> None:
        """Record the start of a tier attempt within a submission.

        Args:
            session_id: Submission session ID
            tier: Tier identifier (T1, T2, T3)
            started_at: ISO timestamp when tier started
        """
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO tier_attempts
                   (session_id, tier, started_at)
                   VALUES (?, ?, ?)""",
                (session_id, tier, started_at),
            )

    def record_tier_result(
        self,
        session_id: str,
        tier: str,
        success: bool,
        duration_sec: float,
        tokens_used: int = 0,
        error_type: Optional[str] = None,
    ) -> None:
        """Record the result of a tier attempt.

        Args:
            session_id: Submission session ID
            tier: Tier identifier (T1, T2, T3)
            success: Whether tier succeeded
            duration_sec: Tier execution duration in seconds
            tokens_used: LLM tokens consumed (T2/T3 only)
            error_type: Error category if failed (e.g., CAPTCHA_TIMEOUT, SELECTOR_NOT_FOUND)
        """
        ended_at = datetime.utcnow().isoformat()
        success_int = 1 if success else 0

        with self.connection() as conn:
            conn.execute(
                """UPDATE tier_attempts
                   SET success = ?, duration_sec = ?, tokens_used = ?,
                       error_type = ?, ended_at = ?
                   WHERE session_id = ? AND tier = ?""",
                (success_int, duration_sec, tokens_used, error_type, ended_at, session_id, tier),
            )

    def record_submission_end(
        self,
        session_id: str,
        success: bool,
        total_duration_sec: float,
        tiers_attempted: List[str],
        final_tier: Optional[str],
    ) -> None:
        """Record the end of a submission session.

        Args:
            session_id: Submission session ID
            success: Whether submission ultimately succeeded
            total_duration_sec: Total submission duration in seconds
            tiers_attempted: List of tiers attempted in order
            final_tier: Last tier attempted (where outcome determined)
        """
        ended_at = datetime.utcnow().isoformat()
        success_int = 1 if success else 0
        tiers_json = json.dumps(tiers_attempted)

        with self.connection() as conn:
            conn.execute(
                """UPDATE submission_telemetry
                   SET success = ?, total_duration_sec = ?, tiers_attempted = ?,
                       final_tier = ?, ended_at = ?
                   WHERE session_id = ?""",
                (success_int, total_duration_sec, tiers_json, final_tier, ended_at, session_id),
            )

    def get_metrics(self, since_hours: float = 24.0) -> Dict[str, Any]:
        """Aggregate telemetry metrics over a time window.

        Args:
            since_hours: Lookback window in hours from now

        Returns:
            Dict with keys:
            - total_submissions: int
            - success_rate: float (0.0-1.0)
            - avg_duration_sec: float
            - tier_distribution: dict {tier: fraction}
            - token_costs: dict {tier: total_tokens}
            - error_breakdown: dict {error_type: count}
        """
        cutoff = datetime.utcnow() - timedelta(hours=since_hours)
        cutoff_iso = cutoff.isoformat()

        with self.connection() as conn:
            # Total completed submissions (has ended_at)
            total_row = conn.execute(
                """SELECT COUNT(*) FROM submission_telemetry
                   WHERE ended_at IS NOT NULL AND started_at >= ?""",
                (cutoff_iso,),
            ).fetchone()
            total = total_row[0]

            if total == 0:
                return {
                    "total_submissions": 0,
                    "success_rate": 0.0,
                    "avg_duration_sec": 0.0,
                    "tier_distribution": {},
                    "token_costs": {},
                    "error_breakdown": {},
                }

            # Success rate
            success_row = conn.execute(
                """SELECT COUNT(*) FROM submission_telemetry
                   WHERE ended_at IS NOT NULL AND success = 1 AND started_at >= ?""",
                (cutoff_iso,),
            ).fetchone()
            success_count = success_row[0]
            success_rate = success_count / total

            # Avg duration
            avg_row = conn.execute(
                """SELECT AVG(total_duration_sec) FROM submission_telemetry
                   WHERE ended_at IS NOT NULL AND started_at >= ?""",
                (cutoff_iso,),
            ).fetchone()
            avg_duration = avg_row[0] or 0.0

            # Tier distribution: fraction of submissions that resolved at each final_tier
            tier_rows = conn.execute(
                """SELECT final_tier, COUNT(*) as cnt FROM submission_telemetry
                   WHERE ended_at IS NOT NULL AND final_tier IS NOT NULL AND started_at >= ?
                   GROUP BY final_tier""",
                (cutoff_iso,),
            ).fetchall()
            tier_distribution = {row[0]: row[1] / total for row in tier_rows if row[0]}

            # Token costs per tier: sum of tokens_used from tier_attempts for completed sessions
            token_rows = conn.execute(
                """SELECT ta.tier, SUM(ta.tokens_used) as total_tokens
                   FROM tier_attempts ta
                   JOIN submission_telemetry st ON ta.session_id = st.session_id
                   WHERE st.ended_at IS NOT NULL AND st.started_at >= ?
                     AND ta.tokens_used > 0
                   GROUP BY ta.tier""",
                (cutoff_iso,),
            ).fetchall()
            token_costs = {row[0]: row[1] for row in token_rows if row[0]}

            # Error breakdown: count of each error_type from failed tier attempts
            error_rows = conn.execute(
                """SELECT ta.error_type, COUNT(*) as cnt
                   FROM tier_attempts ta
                   JOIN submission_telemetry st ON ta.session_id = st.session_id
                   WHERE st.ended_at IS NOT NULL AND st.started_at >= ?
                     AND ta.error_type IS NOT NULL
                   GROUP BY ta.error_type
                   ORDER BY cnt DESC""",
                (cutoff_iso,),
            ).fetchall()
            error_breakdown = {row[0]: row[1] for row in error_rows if row[0]}

        return {
            "total_submissions": total,
            "success_rate": success_rate,
            "avg_duration_sec": avg_duration,
            "tier_distribution": tier_distribution,
            "token_costs": token_costs,
            "error_breakdown": error_breakdown,
        }
