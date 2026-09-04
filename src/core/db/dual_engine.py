"""Dual-database SQLite engine for isolated checkpoints and telemetry in WAL mode."""

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator, Dict, Optional

from src.core.db.connection_pool import ConnectionPool
from src.core.cache.redis_cache import RedisCache

_DB_PATHS: Dict[str, str] = {
    "checkpoints": "./data/checkpoints.db",
    "telemetry": "./data/telemetry.db",
}

# Connection pools per database
_POOLS: Dict[str, ConnectionPool] = {}

# Optional cache layer
_CACHE: Optional[RedisCache] = None

# Pool size configuration
_POOL_SIZE: int = 5


def get_checkpoint_db_path() -> str:
    """Return the currently configured checkpoints database path."""
    return _DB_PATHS["checkpoints"]


def get_telemetry_db_path() -> str:
    """Return the currently configured telemetry database path."""
    return _DB_PATHS["telemetry"]


def init_dual_database_pool(
    checkpoints_path: str = "./data/checkpoints.db",
    telemetry_path: str = "./data/telemetry.db",
    pool_size: int = 5,
    redis_url: Optional[str] = None,
) -> None:
    """Initialize SQLite connections for checkpoints and telemetry with WAL mode and tables.

    Args:
        checkpoints_path: Path to checkpoints database
        telemetry_path: Path to telemetry database
        pool_size: Number of connections per pool (default: 5)
        redis_url: Optional Redis URL for caching layer
    """
    global _CACHE, _POOL_SIZE

    _DB_PATHS["checkpoints"] = checkpoints_path
    _DB_PATHS["telemetry"] = telemetry_path
    _POOL_SIZE = pool_size

    for name, path in _DB_PATHS.items():
        dir_path = os.path.dirname(os.path.abspath(path))
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with sqlite3.connect(path, timeout=30.0) as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("PRAGMA synchronous = NORMAL;")

            if name == "telemetry":
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_spans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        span_id TEXT,
                        event TEXT,
                        tokens INTEGER,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_audit_spans_span_id
                    ON audit_spans(span_id);
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_audit_spans_created_at
                    ON audit_spans(created_at);
                    """
                )
            elif name == "checkpoints":
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS job_locks (
                        job_id TEXT PRIMARY KEY,
                        locked_by TEXT,
                        locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP
                    );
                    """
                )
                conn.execute(
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
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_job_locks_expires_at
                    ON job_locks(expires_at);
                    """
                )
            conn.commit()

    # Create connection pools
    for name, path in _DB_PATHS.items():
        if name in _POOLS:
            _POOLS[name].close_all()
        _POOLS[name] = ConnectionPool(path, pool_size=pool_size)

    # Initialize optional cache
    if redis_url:
        _CACHE = RedisCache(redis_url=redis_url)


def get_cache() -> Optional[RedisCache]:
    """Get the cache instance (may be None if not configured)."""
    return _CACHE


def get_pool(db_name: str = "checkpoints") -> ConnectionPool:
    """Get the connection pool for a specific database.

    Args:
        db_name: Database name ('checkpoints' or 'telemetry')

    Returns:
        ConnectionPool instance

    Raises:
        RuntimeError: If pool not initialized
    """
    if db_name not in _POOLS:
        raise RuntimeError(f"Pool for '{db_name}' not initialized. Call init_dual_database_pool first.")
    return _POOLS[db_name]


@contextmanager
def get_connection(db_name: str = "checkpoints") -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional SQLite connection configured with WAL and 30s busy timeout.

    Uses connection pool if initialized, falls back to direct connection otherwise.

    Args:
        db_name: Database name ('checkpoints' or 'telemetry')
    """
    # Use pool if available
    if db_name in _POOLS:
        with _POOLS[db_name].connection() as conn:
            yield conn
        return

    # Fallback to direct connection (backward compatibility)
    path = _DB_PATHS.get(db_name, _DB_PATHS["checkpoints"])
    conn = sqlite3.connect(path, timeout=30.0)
    try:
        conn.execute("PRAGMA busy_timeout = 30000;")
        yield conn
    finally:
        conn.close()


def close_all_pools() -> None:
    """Close all connection pools and cache."""
    global _CACHE
    for pool in _POOLS.values():
        pool.close_all()
    _POOLS.clear()
    if _CACHE:
        # RedisCache.close() is async but we call it synchronously here
        # Clear memory cache immediately; Redis connection will be cleaned up by GC
        _CACHE._memory_cache.clear()
        _CACHE = None
