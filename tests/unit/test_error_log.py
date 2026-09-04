"""Tests for persistent structured error logging."""

import importlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Dynamic import for error_log module
_error_mod = importlib.import_module("src.core.db.error_log")
ErrorEvent = _error_mod.ErrorEvent
ErrorLogRepository = _error_mod.ErrorLogRepository
log_error = _error_mod.log_error


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database path."""
    return str(tmp_path / "test.db")


# ─── ErrorEvent Tests ────────────────────────────────────────────────────────


class TestErrorEvent:
    def test_create_minimal(self):
        event = ErrorEvent(
            source="crawler",
            component="greenhouse_crawler",
            error_type="HTTP_404",
            message="Board not found",
        )
        assert event.id
        assert event.timestamp
        assert event.source == "crawler"
        assert event.component == "greenhouse_crawler"
        assert event.error_type == "HTTP_404"
        assert event.message == "Board not found"
        assert event.resolved is False

    def test_create_full(self):
        event = ErrorEvent(
            source="gateway",
            component="alibaba_provider",
            error_type="RATE_LIMIT",
            message="Rate limited",
            company="TestCo",
            portal_type="greenhouse",
            board_token="testco",
            http_status=429,
            metadata={"retry_after": 60},
        )
        assert event.company == "TestCo"
        assert event.http_status == 429
        assert event.metadata["retry_after"] == 60

    def test_to_dict(self):
        event = ErrorEvent(
            source="crawler",
            component="test",
            error_type="TEST",
            message="test message",
        )
        d = event.to_dict()
        assert d["source"] == "crawler"
        assert d["component"] == "test"
        assert d["error_type"] == "TEST"
        assert d["message"] == "test message"
        assert "id" in d
        assert "timestamp" in d

    def test_auto_generated_id(self):
        e1 = ErrorEvent(source="a", component="b", error_type="c", message="d")
        e2 = ErrorEvent(source="a", component="b", error_type="c", message="d")
        assert e1.id != e2.id

    def test_auto_generated_timestamp(self):
        event = ErrorEvent(source="a", component="b", error_type="c", message="d")
        assert "T" in event.timestamp  # ISO format


# ─── ErrorLogRepository Tests ────────────────────────────────────────────────


class TestErrorLogRepository:
    def test_ensure_table(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        table_names = [t[0] for t in tables]
        assert "crawler_errors" in table_names

    def test_log_and_retrieve(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)
        event = ErrorEvent(
            source="crawler",
            component="greenhouse_crawler",
            error_type="HTTP_404",
            message="Board not found",
            company="TestCo",
        )
        repo.log_error(event)

        errors = repo.get_recent_errors(limit=10)
        assert len(errors) == 1
        assert errors[0].company == "TestCo"
        assert errors[0].error_type == "HTTP_404"

    def test_get_unresolved_errors(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)

        # Log 3 errors
        for i in range(3):
            repo.log_error(ErrorEvent(
                source="crawler",
                component=f"comp_{i}",
                error_type="TEST",
                message=f"Error {i}",
            ))

        # Resolve one
        errors = repo.get_recent_errors(limit=10)
        repo.mark_resolved(errors[0].id)

        unresolved = repo.get_unresolved_errors(since_hours=1)
        assert len(unresolved) == 2

    def test_get_errors_by_company(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)

        repo.log_error(ErrorEvent(source="a", component="b", error_type="c", message="d", company="Acme"))
        repo.log_error(ErrorEvent(source="a", component="b", error_type="c", message="d", company="Acme"))
        repo.log_error(ErrorEvent(source="a", component="b", error_type="c", message="d", company="Other"))

        errors = repo.get_errors_by_company("Acme")
        assert len(errors) == 2

    def test_mark_resolved(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)
        event = ErrorEvent(source="a", component="b", error_type="c", message="d")
        repo.log_error(event)

        assert repo.mark_resolved(event.id) is True
        errors = repo.get_unresolved_errors(since_hours=1)
        assert len(errors) == 0

    def test_mark_resolved_nonexistent(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)
        assert repo.mark_resolved("nonexistent-id") is False

    def test_mark_company_resolved(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)

        repo.log_error(ErrorEvent(source="a", component="b", error_type="c", message="d", company="TestCo", portal_type="greenhouse"))
        repo.log_error(ErrorEvent(source="a", component="b", error_type="c", message="d", company="TestCo", portal_type="lever"))
        repo.log_error(ErrorEvent(source="a", component="b", error_type="c", message="d", company="OtherCo"))

        count = repo.mark_company_resolved("TestCo", portal_type="greenhouse")
        assert count == 1

        unresolved = repo.get_unresolved_errors(since_hours=1)
        assert len(unresolved) == 2  # lever + OtherCo

    def test_get_error_stats(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)

        repo.log_error(ErrorEvent(source="crawler", component="gh", error_type="HTTP_404", message="m", company="A"))
        repo.log_error(ErrorEvent(source="crawler", component="gh", error_type="HTTP_404", message="m", company="A"))
        repo.log_error(ErrorEvent(source="gateway", component="alibaba", error_type="RATE_LIMIT", message="m"))

        stats = repo.get_error_stats()
        assert stats["total"] == 3
        assert stats["unresolved"] == 3
        assert stats["by_source"]["crawler"] == 2
        assert stats["by_source"]["gateway"] == 1
        assert stats["by_type"]["HTTP_404"] == 2
        assert stats["top_companies"]["A"] == 2

    def test_cleanup_old_errors(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)

        # Insert an old resolved error
        old_ts = "2020-01-01T00:00:00"
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO crawler_errors (id, source, component, error_type, message, timestamp, resolved) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old-id", "test", "test", "TEST", "old", old_ts, 1),
        )
        conn.commit()
        conn.close()

        # Insert a new unresolved error
        repo.log_error(ErrorEvent(source="a", component="b", error_type="c", message="d"))

        deleted = repo.cleanup_old_errors(days=1)
        assert deleted == 1

        errors = repo.get_recent_errors(limit=10)
        assert len(errors) == 1

    def test_get_recent_errors_filter_by_source(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)
        repo.log_error(ErrorEvent(source="crawler", component="a", error_type="b", message="c"))
        repo.log_error(ErrorEvent(source="gateway", component="a", error_type="b", message="c"))
        repo.log_error(ErrorEvent(source="crawler", component="a", error_type="b", message="c"))

        errors = repo.get_recent_errors(limit=10, source="crawler")
        assert len(errors) == 2
        assert all(e.source == "crawler" for e in errors)

    def test_metadata_serialization(self, tmp_db):
        repo = ErrorLogRepository(db_path=tmp_db)
        event = ErrorEvent(
            source="test",
            component="test",
            error_type="TEST",
            message="test",
            metadata={"key": "value", "nested": {"a": 1}},
        )
        repo.log_error(event)

        errors = repo.get_recent_errors(limit=1)
        assert errors[0].metadata["key"] == "value"
        assert errors[0].metadata["nested"]["a"] == 1


# ─── log_error() Function Tests ──────────────────────────────────────────────


class TestLogError:
    def test_log_error_persists_to_db(self, tmp_db, monkeypatch):
        # Reset module singleton
        monkeypatch.setattr(_error_mod, "_repo", None)
        event = log_error(
            source="test",
            component="test_comp",
            error_type="TEST_ERROR",
            message="test message",
            db_path=tmp_db,
        )
        assert event.id

        repo = ErrorLogRepository(db_path=tmp_db)
        errors = repo.get_recent_errors(limit=1)
        assert len(errors) == 1
        assert errors[0].source == "test"
        assert errors[0].component == "test_comp"

    def test_log_error_with_all_fields(self, tmp_db, monkeypatch):
        monkeypatch.setattr(_error_mod, "_repo", None)
        event = log_error(
            source="crawler",
            component="greenhouse_crawler",
            error_type="HTTP_404",
            message="Board not found",
            company="TestCo",
            portal_type="greenhouse",
            board_token="testco",
            http_status=404,
            metadata={"url": "https://example.com"},
            db_path=tmp_db,
        )

        repo = ErrorLogRepository(db_path=tmp_db)
        errors = repo.get_recent_errors(limit=1)
        assert errors[0].company == "TestCo"
        assert errors[0].portal_type == "greenhouse"
        assert errors[0].board_token == "testco"
        assert errors[0].http_status == 404
        assert errors[0].metadata["url"] == "https://example.com"

    def test_log_error_broadcasts_to_agent_logs(self, tmp_db, monkeypatch):
        monkeypatch.setattr(_error_mod, "_repo", None)

        # Mock AGENT_LOGS
        mock_logs = []

        class MockSubagentState:
            AGENT_LOGS = mock_logs

            @staticmethod
            def log_agent_event(message, level="INFO"):
                mock_logs.append({"message": message, "level": level})

        import sys
        # Create mock module
        mock_mod = MockSubagentState()
        sys.modules["src.interface.api.subagent_state"] = mock_mod

        try:
            log_error(
                source="test",
                component="test",
                error_type="TEST",
                message="broadcast test",
                db_path=tmp_db,
            )
            assert len(mock_logs) == 1
            assert "CRAWLER_ERROR" in mock_logs[0]["message"]
            assert mock_logs[0]["level"] == "ERROR"
        finally:
            sys.modules.pop("src.interface.api.subagent_state", None)
