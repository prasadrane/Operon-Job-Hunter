"""SQLite database schema initialization and migrations for CareerGraph AI."""

import json
import os
import shutil
import sqlite3
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def init_db(db_path: str = "./data/careergraph.db") -> None:
    """Initialize the SQLite database with WAL mode, foreign keys, tables, and indices.

    Args:
        db_path: Filesystem path to the SQLite database file.
    """
    dirname = os.path.dirname(os.path.abspath(db_path))
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Performance and integrity pragmas
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA synchronous = NORMAL;")

        # 1. Jobs Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                portal_type TEXT DEFAULT 'generic',
                source TEXT DEFAULT 'scanner',
                status TEXT NOT NULL DEFAULT 'discovered',
                location TEXT,
                description TEXT,
                h1b_sponsored INTEGER,
                posted_at TEXT,
                discovered_at TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                raw_data TEXT
            );
            """
        )

        # 2. Evaluations Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                fit_score REAL NOT NULL DEFAULT 0.0,
                score REAL,
                reason TEXT,
                block_scores TEXT,
                work_auth_blocker INTEGER DEFAULT 0,
                is_ghost_job INTEGER DEFAULT 0,
                evaluated_at TEXT NOT NULL
            );
            """
        )

        # 3. Artifacts Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                resume_pdf_path TEXT,
                resume_json_path TEXT,
                cover_letter_path TEXT,
                qa_answers TEXT,
                linkedin_outreach TEXT,
                tailored_at TEXT NOT NULL
            );
            """
        )

        # 4. Applications Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'applied',
                applied_at TEXT NOT NULL,
                portal_url TEXT,
                resume_pdf_path TEXT,
                submission_receipt_id TEXT,
                followup_due_date TEXT,
                last_status_update TEXT,
                notes TEXT
            );
            """
        )

        # Schema migration check for posted_at
        cursor.execute("PRAGMA table_info(jobs);")
        columns = [col[1] for col in cursor.fetchall()]
        if "posted_at" not in columns:
            cursor.execute("ALTER TABLE jobs ADD COLUMN posted_at TEXT;")

        # Indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_job_id ON evaluations(job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_job_id ON artifacts(job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);")

        conn.commit()
    finally:
        conn.close()


# ─── Schema Migration (v2.5) ────────────────────────────────────────────────


def migrate_schema(
    conn: sqlite3.Connection,
    backup_dir: str = "./data/backups",
) -> None:
    """Migrate evaluations table to v2.5 schema.

    Creates pre-migration backup, adds new columns (hard_blocks, soft_flags,
    validation_level, provenance_hash), and backfills legacy records.
    Atomic transaction — rolls back on any failure.

    Args:
        conn: Open SQLite connection (caller manages lifecycle).
        backup_dir: Directory for backup file. Defaults to ./data/backups.

    Raises:
        sqlite3.Error: If migration fails (transaction rolled back).
    """
    # 1. Create pre-migration backup
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"careergraph_pre_v25_{timestamp}.db")

    # Use SQLite Online Backup API
    backup_conn = sqlite3.connect(backup_path)
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()

    logger.info("Pre-migration backup created: %s", backup_path)

    # 2. Check current columns
    cursor = conn.execute("PRAGMA table_info(evaluations)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    new_columns = ["hard_blocks", "soft_flags", "validation_level", "provenance_hash"]
    columns_to_add = [c for c in new_columns if c not in existing_columns]

    if not columns_to_add:
        logger.info("Schema already migrated, no new columns needed")
        return

    # 3. Atomic migration with rollback
    try:
        # Explicitly begin transaction (ALTER TABLE is DDL and may not trigger implicit tx)
        conn.execute("BEGIN")
        try:
            # Add new columns
            for col in columns_to_add:
                if col == "hard_blocks":
                    conn.execute("ALTER TABLE evaluations ADD COLUMN hard_blocks TEXT")
                elif col == "soft_flags":
                    conn.execute("ALTER TABLE evaluations ADD COLUMN soft_flags TEXT")
                elif col == "validation_level":
                    conn.execute("ALTER TABLE evaluations ADD COLUMN validation_level TEXT DEFAULT 'standard'")
                elif col == "provenance_hash":
                    conn.execute("ALTER TABLE evaluations ADD COLUMN provenance_hash TEXT")

            # 4. Backfill legacy records
            # Check if legacy columns exist before backfilling
            cursor = conn.execute("PRAGMA table_info(evaluations)")
            all_columns = {row[1] for row in cursor.fetchall()}

            if "work_auth_blocker" in all_columns:
                # work_auth_blocker=1 → hard_blocks contains "work_auth"
                conn.execute("""
                    UPDATE evaluations
                    SET hard_blocks = json_array('work_auth')
                    WHERE work_auth_blocker = 1
                      AND (hard_blocks IS NULL OR hard_blocks = '[]')
                """)

            if "is_ghost_job" in all_columns:
                # is_ghost_job=1 → hard_blocks contains "ghost_job"
                # Append to existing array or create new one
                conn.execute("""
                    UPDATE evaluations
                    SET hard_blocks = CASE
                        WHEN hard_blocks IS NULL OR hard_blocks = '[]'
                            THEN json_array('ghost_job')
                        ELSE json_insert(hard_blocks, '$[#]', 'ghost_job')
                    END
                    WHERE is_ghost_job = 1
                """)

            # fit_score < 72 → soft_flags contains "low_fit_score"
            conn.execute("""
                UPDATE evaluations
                SET soft_flags = json_array('low_fit_score')
                WHERE fit_score < 72.0
                  AND (soft_flags IS NULL OR soft_flags = '[]')
            """)

            # Initialize empty arrays for records without flags
            conn.execute("""
                UPDATE evaluations
                SET hard_blocks = '[]'
                WHERE hard_blocks IS NULL
            """)
            conn.execute("""
                UPDATE evaluations
                SET soft_flags = '[]'
                WHERE soft_flags IS NULL
            """)

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        logger.info("Schema migration completed successfully")

    except Exception as e:
        logger.error("Schema migration failed, rolling back: %s", e)
        # Log error to error_log.db
        _log_migration_error(e)
        raise


def _log_migration_error(error: Exception) -> None:
    """Log migration failure to data/error_log.db."""
    try:
        error_db_path = "./data/error_log.db"
        os.makedirs(os.path.dirname(error_db_path), exist_ok=True)
        error_conn = sqlite3.connect(error_db_path)
        error_conn.execute("""
            CREATE TABLE IF NOT EXISTS migration_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        error_conn.execute(
            "INSERT INTO migration_errors (error_type, message, timestamp) VALUES (?, ?, ?)",
            (type(error).__name__, str(error), datetime.utcnow().isoformat()),
        )
        error_conn.commit()
        error_conn.close()
    except Exception as log_err:
        logger.error("Failed to log migration error: %s", log_err)
