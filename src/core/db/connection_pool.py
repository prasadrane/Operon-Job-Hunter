"""SQLite connection pool with thread-safe connection management."""

import sqlite3
import queue
import threading
import logging
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Thread-safe SQLite connection pool.

    Manages a fixed pool of reusable connections with automatic
    creation, checkout, checkin, and cleanup.
    """

    def __init__(self, database_url: str, pool_size: int = 10, **connect_kwargs):
        """
        Initialize connection pool.

        Args:
            database_url: Path to SQLite database file
            pool_size: Maximum number of connections in pool (default: 10)
            **connect_kwargs: Additional args passed to sqlite3.connect()
        """
        self._database_url = database_url
        self._pool_size = pool_size
        self._connect_kwargs = connect_kwargs
        self._pool: queue.Queue = queue.Queue(maxsize=pool_size)
        self._created_count = 0
        self._lock = threading.Lock()
        self._closed = False

        # Pre-populate pool with connections
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        """Create initial connections and add to pool."""
        for _ in range(self._pool_size):
            conn = self._create_connection()
            self._pool.put_nowait(conn)

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with WAL mode."""
        conn = sqlite3.connect(self._database_url, timeout=30.0, **self._connect_kwargs)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        with self._lock:
            self._created_count += 1
        return conn

    def get_connection(self) -> sqlite3.Connection:
        """
        Get a connection from the pool.

        Returns:
            SQLite connection

        Raises:
            RuntimeError: If pool is closed
            queue.Empty: If no connections available (should not happen with proper sizing)
        """
        if self._closed:
            raise RuntimeError("Connection pool is closed")

        conn = self._pool.get(timeout=5.0)

        # Test connection health, recreate if needed
        try:
            conn.execute("SELECT 1")
        except Exception:
            logger.warning("Stale connection detected, recreating")
            conn = self._create_connection()

        return conn

    def release_connection(self, conn: sqlite3.Connection) -> None:
        """
        Return a connection to the pool.

        Args:
            conn: Connection to release back to pool
        """
        if self._closed:
            try:
                conn.close()
            except Exception:
                pass
            return

        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            # Pool full, close excess connection
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def connection(self):
        """
        Context manager for automatic connection checkout/checkin.

        Usage:
            with pool.connection() as conn:
                conn.execute("SELECT ...")
        """
        conn = self.get_connection()
        try:
            yield conn
        finally:
            self.release_connection(conn)

    def close_all(self) -> None:
        """Close all connections in the pool."""
        self._closed = True
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Exception:
                pass

    @property
    def size(self) -> int:
        """Current number of connections in pool."""
        return self._pool.qsize()

    @property
    def pool_size(self) -> int:
        """Maximum pool size."""
        return self._pool_size

    def __del__(self):
        """Cleanup on garbage collection."""
        if not self._closed:
            self.close_all()
