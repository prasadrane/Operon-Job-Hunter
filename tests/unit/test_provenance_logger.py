"""Tests for provenance logger and schema migration (task-3)."""

import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database with legacy evaluations table."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Jobs table
    conn.execute("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            discovered_at TEXT NOT NULL
        )
    """)

    # Legacy evaluations table (pre-v2.5)
    conn.execute("""
        CREATE TABLE evaluations (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            fit_score REAL NOT NULL DEFAULT 0.0,
            score REAL,
            reason TEXT,
            block_scores TEXT,
            work_auth_blocker INTEGER DEFAULT 0,
            is_ghost_job INTEGER DEFAULT 0,
            evaluated_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def populated_db(temp_db):
    """Database with legacy records for backfill tests."""
    conn = sqlite3.connect(temp_db)
    # Insert jobs
    conn.execute("INSERT INTO jobs (id, company, title, url, discovered_at) VALUES ('j1', 'Acme', 'Dev', 'http://a.com', '2025-01-01')")
    conn.execute("INSERT INTO jobs (id, company, title, url, discovered_at) VALUES ('j2', 'Beta', 'Eng', 'http://b.com', '2025-01-02')")
    conn.execute("INSERT INTO jobs (id, company, title, url, discovered_at) VALUES ('j3', 'Gamma', 'QA', 'http://c.com', '2025-01-03')")
    conn.execute("INSERT INTO jobs (id, company, title, url, discovered_at) VALUES ('j4', 'Delta', 'SRE', 'http://d.com', '2025-01-04')")

    # work_auth_blocker=1 → hard_blocks
    conn.execute("INSERT INTO evaluations (id, job_id, fit_score, evaluated_at, work_auth_blocker) VALUES ('e1', 'j1', 85.0, '2025-01-01', 1)")
    # is_ghost_job=1 → hard_blocks
    conn.execute("INSERT INTO evaluations (id, job_id, fit_score, evaluated_at, is_ghost_job) VALUES ('e2', 'j2', 80.0, '2025-01-02', 1)")
    # fit_score < 72 → soft_flags
    conn.execute("INSERT INTO evaluations (id, job_id, fit_score, evaluated_at) VALUES ('e3', 'j3', 60.0, '2025-01-03')")
    # Clean record
    conn.execute("INSERT INTO evaluations (id, job_id, fit_score, evaluated_at) VALUES ('e4', 'j4', 90.0, '2025-01-04')")
    conn.commit()
    conn.close()
    return temp_db


# ─── ProvenanceLogger Tests ──────────────────────────────────────────────────


class TestProvenanceLogger:
    """Tests for ProvenanceLogger class."""

    @pytest.fixture
    def logger(self, tmp_path):
        from src.core.db.provenance_logger import ProvenanceLogger
        db_path = tmp_path / "prov.db"
        return ProvenanceLogger(str(db_path))

    def test_log_execution_returns_32_byte_hash(self, logger):
        """log_execution returns consistent 32-byte SHA-256 hash."""
        h = logger.log_execution("prompt1", "qwen3.6-flash", "v2.5", "snap123")
        assert isinstance(h, str)
        assert len(h) == 64  # 32 bytes = 64 hex chars

    def test_log_execution_consistent_hash(self, logger):
        """Same inputs produce same hash."""
        h1 = logger.log_execution("prompt1", "qwen3.6-flash", "v2.5", "snap123")
        h2 = logger.log_execution("prompt1", "qwen3.6-flash", "v2.5", "snap123")
        assert h1 == h2

    def test_log_execution_different_inputs_different_hash(self, logger):
        """Different inputs produce different hash."""
        h1 = logger.log_execution("prompt1", "qwen3.6-flash", "v2.5", "snap123")
        h2 = logger.log_execution("prompt2", "qwen3.6-flash", "v2.5", "snap123")
        assert h1 != h2

    def test_log_execution_hash_is_sha256(self, logger):
        """Hash matches manual SHA-256 computation of inputs."""
        prompt = "test_prompt"
        model_id = "qwen3.6-flash"
        rubric = "v2.5"
        snap = "snap_abc"
        h = logger.log_execution(prompt, model_id, rubric, snap)

        expected = hashlib.sha256(f"{prompt}{model_id}{rubric}{snap}".encode()).hexdigest()
        assert h == expected

    def test_get_provenance_retrieves_metadata(self, logger):
        """get_provenance returns correct metadata by hash."""
        h = logger.log_execution("prompt1", "qwen3.6-flash", "v2.5", "snap123")
        prov = logger.get_provenance(h)

        assert prov is not None
        assert prov["prompt"] == "prompt1"
        assert prov["model_id"] == "qwen3.6-flash"
        assert prov["rubric_version"] == "v2.5"
        assert prov["graph_snapshot_id"] == "snap123"
        assert "logged_at" in prov

    def test_get_provenance_missing_returns_none(self, logger):
        """get_provenance returns None for unknown hash."""
        prov = logger.get_provenance("deadbeef" * 8)
        assert prov is None

    def test_provenance_stored_in_db(self, logger):
        """Provenance records persisted to database."""
        h = logger.log_execution("p", "m", "r", "s")
        prov = logger.get_provenance(h)
        assert prov["hash"] == h


# ─── Schema Migration Tests ─────────────────────────────────────────────────


class TestSchemaMigration:
    """Tests for migrate_schema function."""

    def test_migration_adds_new_columns(self, populated_db):
        """migrate_schema adds hard_blocks, soft_flags, validation_level, provenance_hash."""
        from src.core.db.schema import migrate_schema
        conn = sqlite3.connect(populated_db)
        try:
            migrate_schema(conn, backup_dir=str(Path(populated_db).parent / "backups"))
            cursor = conn.execute("PRAGMA table_info(evaluations)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "hard_blocks" in columns
            assert "soft_flags" in columns
            assert "validation_level" in columns
            assert "provenance_hash" in columns
        finally:
            conn.close()

    def test_migration_creates_backup(self, populated_db, tmp_path):
        """migrate_schema creates backup before altering schema."""
        from src.core.db.schema import migrate_schema
        backup_dir = str(tmp_path / "backups")
        conn = sqlite3.connect(populated_db)
        try:
            migrate_schema(conn, backup_dir=backup_dir)
        finally:
            conn.close()

        # Backup file exists
        backups = list(Path(backup_dir).glob("careergraph_pre_v25*.db"))
        assert len(backups) >= 1

    def test_migration_idempotent(self, populated_db, tmp_path):
        """Running migration twice does not error or duplicate columns."""
        from src.core.db.schema import migrate_schema
        backup_dir = str(tmp_path / "backups")

        conn = sqlite3.connect(populated_db)
        try:
            migrate_schema(conn, backup_dir=backup_dir)
            migrate_schema(conn, backup_dir=backup_dir)  # Second run

            cursor = conn.execute("PRAGMA table_info(evaluations)")
            columns = [row[1] for row in cursor.fetchall()]
            # No duplicates
            assert len(columns) == len(set(columns))
            assert "hard_blocks" in columns
        finally:
            conn.close()

    def test_backfill_work_auth_blocker(self, populated_db, tmp_path):
        """work_auth_blocker=1 → hard_blocks JSON contains work_auth."""
        from src.core.db.schema import migrate_schema
        import json
        conn = sqlite3.connect(populated_db)
        try:
            migrate_schema(conn, backup_dir=str(tmp_path / "backups"))
            row = conn.execute("SELECT hard_blocks FROM evaluations WHERE id='e1'").fetchone()
            hard_blocks = json.loads(row[0]) if row[0] else []
            assert "work_auth" in hard_blocks
        finally:
            conn.close()

    def test_backfill_ghost_job(self, populated_db, tmp_path):
        """is_ghost_job=1 → hard_blocks JSON contains ghost_job."""
        from src.core.db.schema import migrate_schema
        import json
        conn = sqlite3.connect(populated_db)
        try:
            migrate_schema(conn, backup_dir=str(tmp_path / "backups"))
            row = conn.execute("SELECT hard_blocks FROM evaluations WHERE id='e2'").fetchone()
            hard_blocks = json.loads(row[0]) if row[0] else []
            assert "ghost_job" in hard_blocks
        finally:
            conn.close()

    def test_backfill_low_fit_score(self, populated_db, tmp_path):
        """fit_score < 72 → soft_flags JSON contains low_fit_score."""
        from src.core.db.schema import migrate_schema
        import json
        conn = sqlite3.connect(populated_db)
        try:
            migrate_schema(conn, backup_dir=str(tmp_path / "backups"))
            row = conn.execute("SELECT soft_flags FROM evaluations WHERE id='e3'").fetchone()
            soft_flags = json.loads(row[0]) if row[0] else []
            assert "low_fit_score" in soft_flags
        finally:
            conn.close()

    def test_clean_record_no_flags(self, populated_db, tmp_path):
        """Clean record (no blockers, score >= 72) has null/empty hard_blocks and soft_flags."""
        from src.core.db.schema import migrate_schema
        import json
        conn = sqlite3.connect(populated_db)
        try:
            migrate_schema(conn, backup_dir=str(tmp_path / "backups"))
            row = conn.execute("SELECT hard_blocks, soft_flags FROM evaluations WHERE id='e4'").fetchone()
            hard_blocks = json.loads(row[0]) if row[0] else []
            soft_flags = json.loads(row[0]) if row[0] else []
            assert hard_blocks == []
            assert soft_flags == []
        finally:
            conn.close()

    def test_migration_rollback_on_failure(self, tmp_path):
        """If migration fails mid-flight, transaction rolls back and backup restored."""
        from src.core.db.schema import migrate_schema

        db_path = str(tmp_path / "fail.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE evaluations (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                fit_score REAL,
                evaluated_at TEXT
            )
        """)
        conn.execute("INSERT INTO evaluations VALUES ('e1', 'j1', 80.0, '2025-01-01')")
        conn.commit()
        conn.close()

        backup_dir = str(tmp_path / "backups")

        # Make the database file read-only after backup but before ALTER
        # This forces ALTER TABLE to fail, triggering rollback
        conn = sqlite3.connect(db_path)
        original_execute = conn.execute
        alter_count = [0]

        class RollbackTestConn:
            """Wrapper that intercepts execute to force failure on 2nd ALTER."""
            def __init__(self, conn):
                self._conn = conn
                self._alter_count = 0

            def execute(self, sql, params=None):
                if isinstance(sql, str) and "ALTER TABLE" in sql:
                    self._alter_count += 1
                    if self._alter_count >= 2:
                        raise sqlite3.OperationalError("Simulated ALTER failure")
                if params is not None:
                    return self._conn.execute(sql, params)
                return self._conn.execute(sql)

            def executemany(self, sql, params):
                return self._conn.executemany(sql, params)

            def executescript(self, sql):
                return self._conn.executescript(sql)

            def cursor(self):
                return self._conn.cursor()

            def backup(self, target):
                return self._conn.backup(target)

            def commit(self):
                return self._conn.commit()

            def rollback(self):
                return self._conn.rollback()

            def close(self):
                return self._conn.close()

            def __enter__(self):
                self._conn.__enter__()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return self._conn.__exit__(exc_type, exc_val, exc_tb)

        wrapper = RollbackTestConn(conn)

        with pytest.raises(sqlite3.OperationalError, match="Simulated"):
            migrate_schema(wrapper, backup_dir=backup_dir)

        conn.close()

        # Verify: reconnect and check columns NOT added (rollback worked)
        conn2 = sqlite3.connect(db_path)
        cursor = conn2.execute("PRAGMA table_info(evaluations)")
        columns = {row[1] for row in cursor.fetchall()}
        conn2.close()
        assert "hard_blocks" not in columns
        assert "soft_flags" not in columns
