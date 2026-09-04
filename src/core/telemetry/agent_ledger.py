"""Persistent audit ledger for agent decisions (P5a foundation).

Pipeline state is checkpointed but pruned and job-scoped; this ledger is
the durable, queryable, cross-run record every agent decision must land
in ('Agent decisions must be logged for audit trail').
"""
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = "./data/careergraph.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_decisions (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    job_id TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agent_decisions_job ON agent_decisions(job_id);
CREATE INDEX IF NOT EXISTS idx_agent_decisions_agent ON agent_decisions(agent_name);
"""


@dataclass
class AgentDecision:
    """One logged decision. All fields JSON-safe via to_record()."""

    agent_name: str
    decision_type: str
    reasoning: str
    job_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_record(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "decision_type": self.decision_type,
            "reasoning": self.reasoning,
            "job_id": self.job_id,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }


def _db(db_path: Optional[str]) -> str:
    """Resolve at CALL time so tests can monkeypatch DEFAULT_DB_PATH."""
    return db_path if db_path is not None else DEFAULT_DB_PATH


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_ledger_schema(db_path: Optional[str] = None) -> None:
    with _connect(_db(db_path)) as conn:
        conn.executescript(_SCHEMA)


def log_agent_decision(decision: AgentDecision, db_path: Optional[str] = None) -> str:
    db_path = _db(db_path)
    ensure_ledger_schema(db_path)
    rec = decision.to_record()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO agent_decisions "
            "(id, agent_name, decision_type, reasoning, job_id, metadata, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rec["id"], rec["agent_name"], rec["decision_type"], rec["reasoning"],
             rec["job_id"], json.dumps(rec["metadata"]), rec["timestamp"]),
        )
    return rec["id"]


def get_decisions(
    job_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    db_path = _db(db_path)
    ensure_ledger_schema(db_path)
    sql = "SELECT * FROM agent_decisions"
    where, params = [], []
    if job_id:
        where.append("job_id = ?"); params.append(job_id)
    if agent_name:
        where.append("agent_name = ?"); params.append(agent_name)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(int(limit))
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        out.append(d)
    return out
