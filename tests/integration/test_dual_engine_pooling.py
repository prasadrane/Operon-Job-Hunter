"""Integration tests for dual_engine with connection pooling and caching."""

import os
import sqlite3
import tempfile
import time
import asyncio
import pytest

from src.core.db.dual_engine import (
    init_dual_database_pool,
    get_connection,
    get_pool,
    get_cache,
    close_all_pools,
)
from src.core.db.connection_pool import ConnectionPool
from src.core.cache.redis_cache import RedisCache


@pytest.fixture
def temp_dbs():
    """Create temporary database files."""
    fd1, checkpoints_path = tempfile.mkstemp(suffix="_checkpoints.db")
    fd2, telemetry_path = tempfile.mkstemp(suffix="_telemetry.db")
    os.close(fd1)
    os.close(fd2)
    yield checkpoints_path, telemetry_path
    close_all_pools()
    # Windows: must close all handles before unlink; also remove WAL/SHM journal files
    for path in [checkpoints_path, telemetry_path]:
        for suffix in ["", "-wal", "-shm"]:
            p = path + suffix
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except PermissionError:
                pass


class TestDualEnginePooling:
    """Test dual_engine with connection pooling."""

    def test_init_creates_pools(self, temp_dbs):
        """Test initialization creates connection pools."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(checkpoints_path, telemetry_path, pool_size=3)

        pool = get_pool("checkpoints")
        assert isinstance(pool, ConnectionPool)
        assert pool.pool_size == 3

        pool2 = get_pool("telemetry")
        assert isinstance(pool2, ConnectionPool)

    def test_get_connection_uses_pool(self, temp_dbs):
        """Test get_connection uses pool when available."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(checkpoints_path, telemetry_path, pool_size=2)

        with get_connection("checkpoints") as conn:
            assert isinstance(conn, sqlite3.Connection)
            conn.execute("SELECT 1")

    def test_get_connection_backward_compat(self, temp_dbs):
        """Test get_connection works without pool initialization."""
        # Close any existing pools
        close_all_pools()

        checkpoints_path, _ = temp_dbs
        # Direct connection fallback (no pool)
        from src.core.db import dual_engine
        dual_engine._DB_PATHS["checkpoints"] = checkpoints_path

        with get_connection("checkpoints") as conn:
            assert isinstance(conn, sqlite3.Connection)

    def test_tables_created(self, temp_dbs):
        """Test tables are created during initialization."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(checkpoints_path, telemetry_path)

        # Check checkpoints tables
        with get_connection("checkpoints") as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='job_locks'"
            )
            assert cursor.fetchone() is not None

            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='candidate_directives'"
            )
            assert cursor.fetchone() is not None

        # Check telemetry tables
        with get_connection("telemetry") as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_spans'"
            )
            assert cursor.fetchone() is not None

    def test_indices_created(self, temp_dbs):
        """Test indices are created for query optimization."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(checkpoints_path, telemetry_path)

        # Check audit_spans indices
        with get_connection("telemetry") as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_audit%'"
            )
            indices = [row[0] for row in cursor.fetchall()]
            assert "idx_audit_spans_span_id" in indices
            assert "idx_audit_spans_created_at" in indices

        # Check job_locks indices
        with get_connection("checkpoints") as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_job%'"
            )
            indices = [row[0] for row in cursor.fetchall()]
            assert "idx_job_locks_expires_at" in indices

    def test_concurrent_reads_performance(self, temp_dbs):
        """Test 100 concurrent reads complete in under 1 second."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(checkpoints_path, telemetry_path, pool_size=10)

        # Insert test data
        with get_connection("checkpoints") as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS perf_test (id INTEGER, data TEXT)")
            for i in range(100):
                conn.execute(f"INSERT INTO perf_test VALUES ({i}, 'data_{i}')")
            conn.commit()

        import threading

        results = []
        errors = []

        def read_worker(idx):
            try:
                with get_connection("checkpoints") as conn:
                    cursor = conn.execute(f"SELECT data FROM perf_test WHERE id = {idx % 100}")
                    row = cursor.fetchone()
                    results.append(row[0])
            except Exception as e:
                errors.append(str(e))

        start = time.time()
        threads = [threading.Thread(target=read_worker, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.time() - start

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 100
        assert elapsed < 1.0, f"100 concurrent reads took {elapsed:.2f}s (expected < 1s)"

    def test_get_pool_not_initialized(self):
        """Test get_pool raises error when not initialized."""
        close_all_pools()
        with pytest.raises(RuntimeError, match="not initialized"):
            get_pool("nonexistent")

    def test_close_all_pools(self, temp_dbs):
        """Test closing all pools."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(checkpoints_path, telemetry_path)

        close_all_pools()

        with pytest.raises(RuntimeError, match="not initialized"):
            get_pool("checkpoints")


class TestDualEngineCache:
    """Test dual_engine with optional cache layer."""

    def test_cache_not_configured(self, temp_dbs):
        """Test cache is None when not configured."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(checkpoints_path, telemetry_path)

        cache = get_cache()
        assert cache is None

    def test_cache_configured(self, temp_dbs):
        """Test cache is created when redis_url provided."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(
            checkpoints_path, telemetry_path,
            redis_url="redis://localhost:6379/0"
        )

        cache = get_cache()
        assert isinstance(cache, RedisCache)

    @pytest.mark.asyncio
    async def test_cache_operations(self, temp_dbs):
        """Test cache get/set operations through dual_engine."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(
            checkpoints_path, telemetry_path,
            redis_url="redis://localhost:6379/0"
        )

        cache = get_cache()
        assert cache is not None

        await cache.set("test_key", {"data": "test_value"})
        result = await cache.get("test_key")
        assert result == {"data": "test_value"}

        await cache.delete("test_key")
        result = await cache.get("test_key")
        assert result is None

        await cache.close()


class TestDualEngineDataIntegrity:
    """Test data integrity with pooled connections."""

    def test_transaction_isolation(self, temp_dbs):
        """Test transactions are properly isolated."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(checkpoints_path, telemetry_path)

        # Create test table
        with get_connection("checkpoints") as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS isolation_test (id INTEGER, val TEXT)")
            conn.execute("INSERT INTO isolation_test VALUES (1, 'original')")
            conn.commit()

        # Read from different connection
        with get_connection("checkpoints") as conn:
            cursor = conn.execute("SELECT val FROM isolation_test WHERE id = 1")
            row = cursor.fetchone()
            assert row[0] == "original"

    def test_wal_mode_in_pool(self, temp_dbs):
        """Test WAL mode is set on pooled connections."""
        checkpoints_path, telemetry_path = temp_dbs
        init_dual_database_pool(checkpoints_path, telemetry_path)

        with get_connection("checkpoints") as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode == "wal"
