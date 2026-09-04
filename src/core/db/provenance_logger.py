"""Provenance logger with SHA-256 execution signatures.

Tracks LLM execution metadata (prompt, model, rubric version, graph snapshot)
with deterministic SHA-256 hashes for reproducibility and audit trails.
"""

import hashlib
import sqlite3
from datetime import datetime
from typing import Optional


class ProvenanceLogger:
    """Logs execution provenance with SHA-256 content-addressable hashes."""

    def __init__(self, db_path: str = "./data/careergraph.db"):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create provenance_executions table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provenance_executions (
                    hash TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    rubric_version TEXT NOT NULL,
                    graph_snapshot_id TEXT NOT NULL,
                    logged_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _compute_hash(
        self,
        prompt: str,
        model_id: str,
        rubric_version: str,
        graph_snapshot_id: str,
    ) -> str:
        """Compute 32-byte SHA-256 hash from execution parameters."""
        payload = f"{prompt}{model_id}{rubric_version}{graph_snapshot_id}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def log_execution(
        self,
        prompt: str,
        model_id: str,
        rubric_version: str,
        graph_snapshot_id: str,
    ) -> str:
        """Log an execution and return its SHA-256 hash.

        Args:
            prompt: The prompt template or content used.
            model_id: LLM model identifier (e.g. 'qwen3.6-flash').
            rubric_version: Rubric version string (e.g. 'v2.5').
            graph_snapshot_id: Career graph snapshot identifier.

        Returns:
            64-character hex SHA-256 hash (32 bytes).
        """
        hash_val = self._compute_hash(prompt, model_id, rubric_version, graph_snapshot_id)
        logged_at = datetime.utcnow().isoformat()

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO provenance_executions
                   (hash, prompt, model_id, rubric_version, graph_snapshot_id, logged_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (hash_val, prompt, model_id, rubric_version, graph_snapshot_id, logged_at),
            )
            conn.commit()
        finally:
            conn.close()

        return hash_val

    def get_provenance(self, hash: str) -> Optional[dict]:
        """Retrieve execution metadata by hash.

        Args:
            hash: 64-character hex SHA-256 hash.

        Returns:
            Dict with keys: hash, prompt, model_id, rubric_version,
            graph_snapshot_id, logged_at. None if not found.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM provenance_executions WHERE hash = ?",
                (hash,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None

        return dict(row)
