"""Structured logger for CareerGraph AI observability.

Outputs either JSON lines (production) or plain text (development) via
standard library logging.  All extra kwargs are attached to the log record.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class _JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        # Merge any extra fields attached to the record
        for key in ("extra_fields",):
            extra = getattr(record, key, None)
            if extra and isinstance(extra, dict):
                payload.update(extra)
        return json.dumps(payload, default=str)


class _PlainTextFormatter(logging.Formatter):
    """Human-readable plain text format for development."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )


class StructuredLogger:
    """Thin wrapper around stdlib logging with structured event support.

    Usage::

        log = StructuredLogger("pipeline.submission")
        log.info("submission_started", job_id="abc", portal="greenhouse")
    """

    def __init__(self, name: str, json_format: bool = True) -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)
        # Prevent duplicate handlers on repeated instantiation
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                _JSONFormatter() if json_format else _PlainTextFormatter()
            )
            self._logger.addHandler(handler)
        self._json_format = json_format

    # --- Public API ---

    def info(self, event: str, **kwargs: Any) -> None:
        """Log at INFO level with structured context."""
        self._emit(logging.INFO, event, kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log at WARNING level with structured context."""
        self._emit(logging.WARNING, event, kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        """Log at ERROR level with structured context."""
        self._emit(logging.ERROR, event, kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log at DEBUG level with structured context."""
        self._emit(logging.DEBUG, event, kwargs)

    # --- Internals ---

    def _emit(self, level: int, event: str, extra: dict[str, Any]) -> None:
        if extra:
            self._logger.log(level, event, extra={"extra_fields": extra})
        else:
            self._logger.log(level, event)
