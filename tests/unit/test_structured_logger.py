"""Unit tests for StructuredLogger.

Verifies:
1. JSON output when json_format=True
2. Plain text output when json_format=False
3. Structured context kwargs are included
4. Log levels (info, warning, error, debug)
5. Multiple instances don't duplicate handlers
"""

import json
import logging

import pytest

from src.core.logging.structured_logger import StructuredLogger


class CapturingHandler(logging.Handler):
    """Capture log records for assertion."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def capturing_logger():
    """StructuredLogger with a capturing handler for record inspection."""
    log = StructuredLogger.__new__(StructuredLogger)
    log._logger = logging.getLogger(f"test.struct_{id(log)}")
    log._logger.setLevel(logging.DEBUG)
    log._logger.handlers.clear()
    log._logger.propagate = False
    from src.core.logging.structured_logger import _JSONFormatter
    handler = CapturingHandler()
    handler.setFormatter(_JSONFormatter())
    log._logger.addHandler(handler)
    log._json_format = True
    return log


class TestJSONOutput:
    """JSON format logging tests."""

    def test_info_outputs_json(self, capsys):
        log = StructuredLogger("test.json_info", json_format=True)
        log.info("test_event", key="value")
        # Output goes to stderr
        captured = capsys.readouterr()
        line = captured.err.strip().split("\n")[-1]
        data = json.loads(line)
        assert data["level"] == "INFO"
        assert data["event"] == "test_event"
        assert data["key"] == "value"
        assert "timestamp" in data

    def test_warning_outputs_json(self, capsys):
        log = StructuredLogger("test.json_warn", json_format=True)
        log.warning("warn_event", code=42)
        captured = capsys.readouterr()
        line = captured.err.strip().split("\n")[-1]
        data = json.loads(line)
        assert data["level"] == "WARNING"
        assert data["event"] == "warn_event"
        assert data["code"] == 42

    def test_error_outputs_json(self, capsys):
        log = StructuredLogger("test.json_error", json_format=True)
        log.error("err_event", detail="something broke")
        captured = capsys.readouterr()
        line = captured.err.strip().split("\n")[-1]
        data = json.loads(line)
        assert data["level"] == "ERROR"
        assert data["detail"] == "something broke"

    def test_debug_outputs_json(self, capsys):
        log = StructuredLogger("test.json_debug", json_format=True)
        log.debug("dbg_event", x=1)
        captured = capsys.readouterr()
        line = captured.err.strip().split("\n")[-1]
        data = json.loads(line)
        assert data["level"] == "DEBUG"

    def test_no_extra_kwargs(self, capsys):
        log = StructuredLogger("test.json_no_extra", json_format=True)
        log.info("bare_event")
        captured = capsys.readouterr()
        line = captured.err.strip().split("\n")[-1]
        data = json.loads(line)
        assert data["event"] == "bare_event"
        assert data["level"] == "INFO"


class TestPlainTextOutput:
    """Plain text format logging tests."""

    def test_plain_text_format(self, capsys):
        log = StructuredLogger("test.plain", json_format=False)
        log.info("plain_event", extra="data")
        captured = capsys.readouterr()
        line = captured.err.strip().split("\n")[-1]
        # Should NOT be JSON
        assert not line.startswith("{")
        # Should contain the logger name and event
        assert "test.plain" in line
        assert "plain_event" in line
        assert "INFO" in line


class TestRecordStructure:
    """Test that log records contain expected fields via capturing handler."""

    def test_extra_fields_in_record(self, capturing_logger):
        capturing_logger.info("ctx_event", job_id="abc123", portal="greenhouse")
        record = capturing_logger._logger.handlers[0].records[-1]
        assert record.getMessage() == "ctx_event"
        extra = getattr(record, "extra_fields", {})
        assert extra["job_id"] == "abc123"
        assert extra["portal"] == "greenhouse"

    def test_logger_name_propagated(self, capturing_logger):
        capturing_logger.info("name_test")
        record = capturing_logger._logger.handlers[0].records[-1]
        assert record.name.startswith("test.struct_")


class TestHandlerDeduplication:
    """Ensure repeated instantiation doesn't add duplicate handlers."""

    def test_no_duplicate_handlers(self):
        name = "test.nodup_handler"
        log1 = StructuredLogger(name, json_format=True)
        initial_count = len(log1._logger.handlers)
        # Creating another logger with same name should not add more handlers
        log2 = StructuredLogger(name, json_format=True)
        assert len(log2._logger.handlers) == initial_count
