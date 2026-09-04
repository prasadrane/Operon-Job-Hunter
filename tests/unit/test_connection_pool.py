"""Unit tests for SQLite ConnectionPool."""

import os
import sqlite3
import tempfile
import threading
import pytest

from src.core.db.connection_pool import ConnectionPool


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Windows: must close pool before unlink; also remove WAL/SHM journal files
    for suffix in ["", "-wal", "-shm"]:
        p = path + suffix
        try:
            if os.path.exists(p):
                os.unlink(p)
        except PermissionError:
            pass


@pytest.fixture
def pool(temp_db):
    """Create a connection pool for testing."""
    p = ConnectionPool(temp_db, pool_size=3)
    yield p
    p.close_all()


class TestConnectionPool:
    """Test ConnectionPool functionality."""

    def test_pool_creation(self, pool):
        """Test pool creates correct number of connections."""
        assert pool.size == 3
        assert pool.pool_size == 3

    def test_get_release_connection(self, pool):
        """Test getting and releasing a connection."""
        conn = pool.get_connection()
        assert isinstance(conn, sqlite3.Connection)

        pool.release_connection(conn)
        assert pool.size == 3  # Connection returned

    def test_connection_context_manager(self, pool):
        """Test connection context manager."""
        with pool.connection() as conn:
            assert isinstance(conn, sqlite3.Connection)
            conn.execute("SELECT 1")

        # Connection should be returned to pool
        assert pool.size == 3

    def test_pool_respects_size_limit(self, pool):
        """Test pool respects maximum size."""
        connections = []
        for _ in range(3):
            conn = pool.get_connection()
            connections.append(conn)

        # Pool should be empty now
        assert pool.size == 0

        # Release all
        for conn in connections:
            pool.release_connection(conn)

        assert pool.size == 3

    def test_concurrent_access(self, pool):
        """Test thread-safe concurrent access."""
        results = []
        errors = []

        def worker(idx):
            try:
                with pool.connection() as conn:
                    conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER, val TEXT)")
                    conn.execute(f"INSERT INTO test VALUES ({idx}, 'thread_{idx}')")
                    conn.commit()
                    cursor = conn.execute(f"SELECT val FROM test WHERE id = {idx}")
                    row = cursor.fetchone()
                    results.append(row[0])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors in threads: {errors}"
        assert len(results) == 10

    def test_close_all(self, temp_db):
        """Test closing all connections."""
        pool = ConnectionPool(temp_db, pool_size=3)
        pool.close_all()

        with pytest.raises(RuntimeError, match="closed"):
            pool.get_connection()

    def test_get_connection_after_close(self, temp_db):
        """Test getting connection from closed pool raises error."""
        pool = ConnectionPool(temp_db, pool_size=2)
        pool.close_all()

        with pytest.raises(RuntimeError):
            pool.get_connection()

    def test_stale_connection_recovery(self, pool):
        """Test pool recovers from stale connections."""
        conn = pool.get_connection()
        conn.close()  # Simulate stale connection

        # Release the closed connection
        pool.release_connection(conn)

        # Next get should recover (recreate if needed)
        new_conn = pool.get_connection()
        assert isinstance(new_conn, sqlite3.Connection)
        new_conn.execute("SELECT 1")  # Should work
        pool.release_connection(new_conn)

    def test_wal_mode_enabled(self, pool):
        """Test connections use WAL mode."""
        with pool.connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode == "wal"

    def test_connection_execute(self, pool):
        """Test executing queries through pooled connections."""
        with pool.connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO users (name) VALUES ('Alice')")
            conn.commit()

            cursor = conn.execute("SELECT name FROM users")
            row = cursor.fetchone()
            assert row[0] == "Alice"

    def test_release_after_close_discards(self, temp_db):
        """Test releasing connection after pool close discards it."""
        pool = ConnectionPool(temp_db, pool_size=2)
        conn = pool.get_connection()
        pool.close_all()

        # Release should not error, just close the connection
        pool.release_connection(conn)

    def test_multiple_pools_same_db(self, temp_db):
        """Test multiple pools can coexist for same database."""
        pool1 = ConnectionPool(temp_db, pool_size=2)
        pool2 = ConnectionPool(temp_db, pool_size=2)

        with pool1.connection() as conn1:
            conn1.execute("CREATE TABLE IF NOT EXISTS shared (id INTEGER)")
            conn1.commit()

        with pool2.connection() as conn2:
            cursor = conn2.execute("SELECT count(*) FROM shared")
            assert cursor.fetchone()[0] == 0

        pool1.close_all()
        pool2.close_all()
