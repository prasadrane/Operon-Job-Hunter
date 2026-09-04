"""MemGPT-style Self-Editing Core Memory Engine with SQLite Persistence and Quota Enforcement."""

from typing import Dict, Optional
from src.core.db.dual_engine import get_connection

MAX_KEYS: int = 10
MAX_VALUE_CHARS: int = 250

DEFAULT_DIRECTIVES: Dict[str, str] = {
    "target_roles": "Senior Software Engineer, Staff Engineer",
    "sponsorship_required": "Yes (H-1B)",
    "salary_floor": "$170,000",
}


class CoreMemoryManager:
    """Manages candidate core directives (in-context RAM) with tool dispatch, quotas, and SQLite sync."""

    def __init__(self, candidate_id: str = "default", db_name: str = "checkpoints", sync_db: bool = True) -> None:
        """Initialize CoreMemoryManager and load or seed candidate directives.

        Args:
            candidate_id: Identifier for the candidate profile partition (default "default").
            db_name: Target database alias for dual_engine connection (default "checkpoints").
            sync_db: Whether to synchronize changes with SQLite persistence.
        """
        self.candidate_id = candidate_id
        self.db_name = db_name
        self.sync_db = sync_db
        self._candidate_cache: Dict[str, Dict[str, str]] = {}
        self._directives: Dict[str, str] = {}
        self._init_storage()

    def _init_storage(self) -> None:
        """Initialize database table and load existing directives or seed defaults for active candidate."""
        if not self.sync_db:
            if self.candidate_id not in self._candidate_cache:
                self._candidate_cache[self.candidate_id] = dict(DEFAULT_DIRECTIVES)
            self._directives = self._candidate_cache[self.candidate_id]
            return


        with get_connection(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS candidate_directives (
                    candidate_id TEXT DEFAULT 'default',
                    key TEXT,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (candidate_id, key)
                );
                """
            )
            conn.commit()

            # Schema migration: check if candidate_id column exists
            cursor.execute("PRAGMA table_info(candidate_directives);")
            columns = [row[1] for row in cursor.fetchall()]
            if "candidate_id" not in columns:
                cursor.execute("ALTER TABLE candidate_directives ADD COLUMN candidate_id TEXT DEFAULT 'default';")
                conn.commit()

            # Ensure unique index on (candidate_id, key) exists for ON CONFLICT target
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_directives_cand_key ON candidate_directives (candidate_id, key);"
            )
            conn.commit()


            cursor.execute(
                "SELECT key, value FROM candidate_directives WHERE candidate_id = ?;",
                (self.candidate_id,)
            )

            rows = cursor.fetchall()
            if rows:
                self._directives = {row[0]: row[1] for row in rows}
            else:
                self._directives = dict(DEFAULT_DIRECTIVES)
                for k, v in self._directives.items():
                    cursor.execute(
                        """
                        INSERT INTO candidate_directives (candidate_id, key, value, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(candidate_id, key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP;
                        """,
                        (self.candidate_id, k, v),
                    )
                conn.commit()

    def switch_candidate(self, candidate_id: str) -> None:
        """Switch active candidate profile partition and load corresponding directives."""
        self.candidate_id = candidate_id
        self._init_storage()

    def get_directive(self, key: str) -> str:
        """Retrieve the value of a directive by key.

        Args:
            key: Name of the directive.

        Returns:
            The directive string value, or empty string if not found.
        """
        return self._directives.get(key, "")

    def set_directive(self, key: str, value: str) -> None:
        """Set or update a directive with quota validation.

        Args:
            key: Name of the directive.
            value: Value of the directive.

        Raises:
            ValueError: If key quota (max 10) or character quota (max 250) is exceeded.
        """
        if key not in self._directives and len(self._directives) >= MAX_KEYS:
            raise ValueError(f"Key quota exceeded (max {MAX_KEYS} keys). Cannot add key '{key}'.")

        if len(value) > MAX_VALUE_CHARS:
            raise ValueError(
                f"Value length ({len(value)}) exceeds maximum allowed length ({MAX_VALUE_CHARS} chars)."
            )

        self._directives[key] = value

        if self.sync_db:
            with get_connection(self.db_name) as conn:
                conn.execute(
                    """
                    INSERT INTO candidate_directives (candidate_id, key, value, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(candidate_id, key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP;
                    """,
                    (self.candidate_id, key, value),
                )
                conn.commit()

    def delete_directive(self, key: str) -> None:
        """Delete a directive by key.

        Args:
            key: Name of the directive to remove.
        """
        if key in self._directives:
            del self._directives[key]

        if self.sync_db:
            with get_connection(self.db_name) as conn:
                conn.execute(
                    "DELETE FROM candidate_directives WHERE candidate_id = ? AND key = ?;",
                    (self.candidate_id, key),
                )
                conn.commit()

    def list_directives(self) -> Dict[str, str]:
        """Return a copy of all current directives."""
        return dict(self._directives)

    def execute_tool(self, action: str, key: str, value: str) -> Dict[str, str]:
        """Execute a MemGPT-style core memory self-editing tool.

        Args:
            action: Either 'core_memory_append' or 'core_memory_replace'.
            key: The directive key.
            value: The content to append or replace.

        Returns:
            Dict containing the updated directives.

        Raises:
            ValueError: If action is unknown or quotas are violated.
        """
        if action == "core_memory_append":
            curr = self.get_directive(key)
            new_value = f"{curr}{value}"
            self.set_directive(key, new_value)
            return dict(self._directives)
        elif action == "core_memory_replace":
            self.set_directive(key, value)
            return dict(self._directives)
        else:
            raise ValueError(f"Unknown action: {action}. Expected 'core_memory_append' or 'core_memory_replace'.")

    def render_system_prompt_prefix(self) -> str:
        """Render directives into a structured system prompt prefix for in-context RAM."""
        lines = [f"- {k.upper()}: {v}" for k, v in self._directives.items()]
        return "### CANDIDATE CORE DIRECTIVES (IN-CONTEXT RAM):\n" + "\n".join(lines)

    def render_system_ram(self) -> str:
        """Alias for render_system_prompt_prefix."""
        return self.render_system_prompt_prefix()

