"""Unit tests for Dual-DB Persistence Engine and SQLite WAL Pool."""

import asyncio
import json
import sqlite3
import pytest

from src.core.db.dual_engine import (
    init_dual_database_pool,
    get_connection,
    get_checkpoint_db_path,
    get_telemetry_db_path,
)
from src.core.db.telemetry_sink import TelemetrySink


@pytest.mark.asyncio
async def test_dual_db_isolation_and_wal_mode(tmp_path):
    checkpoints_path = str(tmp_path / "checkpoints.db")
    telemetry_path = str(tmp_path / "telemetry.db")

    init_dual_database_pool(checkpoints_path=checkpoints_path, telemetry_path=telemetry_path)

    assert get_checkpoint_db_path() == checkpoints_path
    assert get_telemetry_db_path() == telemetry_path

    # Verify checkpoints DB WAL & busy timeout
    with get_connection("checkpoints") as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        assert cursor.fetchone()[0].upper() == "WAL"
        cursor.execute("PRAGMA busy_timeout;")
        assert cursor.fetchone()[0] == 30000

        # Verify job_locks table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='job_locks';")
        assert cursor.fetchone() is not None

    # Verify telemetry DB WAL & busy timeout & audit_spans table
    with get_connection("telemetry") as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        assert cursor.fetchone()[0].upper() == "WAL"
        cursor.execute("PRAGMA busy_timeout;")
        assert cursor.fetchone()[0] == 30000

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_spans';")
        assert cursor.fetchone() is not None

    # Test TelemetrySink async batch flushing
    sink = TelemetrySink(telemetry_path=telemetry_path, flush_interval=0.05)
    await sink.start()
    for i in range(25):
        await sink.log_span({"span_id": f"span_{i}", "event": "test_step", "tokens": 100})
    await sink.flush_and_close()

    with get_connection("telemetry") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_spans;")
        assert cursor.fetchone()[0] == 25


@pytest.mark.asyncio
async def test_telemetry_sink_tight_drain_on_close(tmp_path):
    telemetry_path = str(tmp_path / "telemetry_drain.db")
    init_dual_database_pool(telemetry_path=telemetry_path)

    sink = TelemetrySink(telemetry_path=telemetry_path, flush_interval=0.01)
    await sink.start()

    # Queue 120 items (more than single 50-item batch to test tight-drain multi-batch flush on close)
    for i in range(120):
        await sink.log_span({"span_id": f"span_{i}", "event": f"event_{i}", "tokens": i * 10})

    await sink.flush_and_close()

    with get_connection("telemetry") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_spans;")
        assert cursor.fetchone()[0] == 120


@pytest.mark.asyncio
async def test_telemetry_sink_metadata_and_log_event(tmp_path):
    telemetry_path = str(tmp_path / "telemetry_meta.db")
    init_dual_database_pool(telemetry_path=telemetry_path)

    sink = TelemetrySink(telemetry_path=telemetry_path, flush_interval=0.01)
    await sink.start()

    await sink.log_event({
        "span_id": "meta_span_1",
        "event": "llm_call",
        "tokens": 450,
        "metadata": {"model": "gemini-1.5-flash", "temperature": 0.2},
    })
    await sink.log_span({
        "span_id": "meta_span_2",
        "event": "raw_str_meta",
        "metadata": "simple string metadata",
    })

    await sink.flush_and_close()

    with get_connection("telemetry") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT span_id, event, tokens, metadata FROM audit_spans ORDER BY id ASC;")
        rows = cursor.fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "meta_span_1"
        assert rows[0][1] == "llm_call"
        assert rows[0][2] == 450
        meta_json = json.loads(rows[0][3])
        assert meta_json["model"] == "gemini-1.5-flash"

        assert rows[1][0] == "meta_span_2"
        assert rows[1][1] == "raw_str_meta"
        assert rows[1][2] == 0
        assert rows[1][3] == "simple string metadata"

