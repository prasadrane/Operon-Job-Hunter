"""Unit tests for robust job posting date and time parser."""

import importlib
from datetime import datetime, timezone, timedelta
import pytest

_dp_mod = importlib.import_module("src.pipeline.1_discovery.date_parser")
parse_job_posted_date = _dp_mod.parse_job_posted_date


def test_parse_iso8601_timestamps():
    """Verify ISO-8601 formatted strings with Z and offset timezones."""
    dt1 = parse_job_posted_date("2026-08-20T14:30:00Z")
    assert dt1 is not None
    assert dt1.year == 2026 and dt1.month == 8 and dt1.day == 20
    assert dt1.hour == 14 and dt1.minute == 30

    dt2 = parse_job_posted_date("2026-08-21T09:15:00-04:00")
    assert dt2 is not None
    # 09:15 -04:00 normalized to UTC is 13:15
    assert dt2.hour == 13 and dt2.minute == 15

    dt3 = parse_job_posted_date("2026-08-22 18:00:00")
    assert dt3 is not None
    assert dt3.day == 22 and dt3.hour == 18


def test_parse_unix_epochs_seconds_and_milliseconds():
    """Verify UNIX timestamps in seconds and Lever-style milliseconds."""
    # 1787400000 -> 2026-08-22
    dt_sec = parse_job_posted_date(1787400000)
    assert dt_sec is not None
    assert dt_sec.year == 2026

    # Milliseconds epoch (Lever API createdAt format: 13 digits)
    dt_ms = parse_job_posted_date(1787400000000)
    assert dt_ms is not None
    assert dt_ms.year == 2026


def test_parse_relative_english_expressions():
    """Verify relative expressions commonly found on Workday and Indeed."""
    now = datetime.now(timezone.utc)

    dt_today = parse_job_posted_date("Posted Today")
    assert dt_today is not None
    assert abs((now - dt_today).total_seconds()) < 3600

    dt_yesterday = parse_job_posted_date("Posted Yesterday")
    assert dt_yesterday is not None
    assert abs((now - timedelta(days=1) - dt_yesterday).total_seconds()) < 7200

    dt_2days = parse_job_posted_date("Posted 2 Days Ago")
    assert dt_2days is not None
    assert abs((now - timedelta(days=2) - dt_2days).total_seconds()) < 7200

    dt_30plus = parse_job_posted_date("Posted 30+ Days Ago")
    assert dt_30plus is not None
    assert (now - dt_30plus).total_seconds() >= (30 * 86400 - 10)

    dt_hours = parse_job_posted_date("3 hours ago")
    assert dt_hours is not None
    assert abs((now - timedelta(hours=3) - dt_hours).total_seconds()) < 300

    dt_just_posted = parse_job_posted_date("Just posted")
    assert dt_just_posted is not None
    assert abs((now - dt_just_posted).total_seconds()) < 300


def test_parse_rfc2822_and_standard_dates():
    """Verify RSS/Atom feed RFC-2822 dates (e.g. RemoteOK/Jobicy/EchoJobs)."""
    dt_rfc = parse_job_posted_date("Wed, 19 Aug 2026 12:00:00 GMT")
    assert dt_rfc is not None
    assert dt_rfc.year == 2026 and dt_rfc.month == 8 and dt_rfc.day == 19
    assert dt_rfc.hour == 12


def test_parse_invalid_or_none_returns_none():
    """Verify invalid strings or None return None gracefully without raising exceptions."""
    assert parse_job_posted_date(None) is None
    assert parse_job_posted_date("") is None
    assert parse_job_posted_date("N/A") is None
    assert parse_job_posted_date("invalid_date_xyz") is None
