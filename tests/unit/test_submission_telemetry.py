"""Unit tests for SubmissionTelemetry.

Tests 1-6 from P3d Task 6 spec:
1. record_submission_start creates session
2. record_tier_attempt logs attempt
3. record_tier_result updates attempt
4. record_submission_end completes session
5. get_metrics returns correct aggregations
6. Metrics handle missing data gracefully
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from src.core.telemetry.submission_telemetry import SubmissionTelemetry


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    import os
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def telemetry(temp_db):
    """Create a SubmissionTelemetry instance with temp DB."""
    return SubmissionTelemetry(db_path=temp_db)


class TestRecordSubmissionStart:
    """Test 1: record_submission_start creates session."""

    def test_creates_session_and_returns_id(self, telemetry):
        """record_submission_start returns a session_id string."""
        session_id = telemetry.record_submission_start(
            job_id="job-123",
            portal_type="greenhouse",
        )
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    def test_session_persisted_in_db(self, telemetry, temp_db):
        """Session row exists in submission_telemetry table."""
        session_id = telemetry.record_submission_start(
            job_id="job-456",
            portal_type="lever",
        )
        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT session_id, job_id, portal_type, started_at FROM submission_telemetry WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == session_id
        assert row[1] == "job-456"
        assert row[2] == "lever"
        assert row[3] is not None  # started_at set

    def test_unique_session_ids(self, telemetry):
        """Each call returns a unique session_id."""
        s1 = telemetry.record_submission_start("job-1", "greenhouse")
        s2 = telemetry.record_submission_start("job-2", "lever")
        assert s1 != s2


class TestRecordTierAttempt:
    """Test 2: record_tier_attempt logs attempt."""

    def test_tier_attempt_logged(self, telemetry, temp_db):
        """record_tier_attempt creates a row in tier_attempts."""
        session_id = telemetry.record_submission_start("job-1", "greenhouse")
        started_at = datetime.utcnow().isoformat()

        telemetry.record_tier_attempt(
            session_id=session_id,
            tier="T1",
            started_at=started_at,
        )

        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT session_id, tier, started_at FROM tier_attempts WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == session_id
        assert row[1] == "T1"
        assert row[2] == started_at

    def test_multiple_tier_attempts(self, telemetry, temp_db):
        """Multiple tiers can be logged for one session."""
        session_id = telemetry.record_submission_start("job-1", "ashby")
        now = datetime.utcnow().isoformat()

        telemetry.record_tier_attempt(session_id, "T1", now)
        telemetry.record_tier_attempt(session_id, "T2", now)

        conn = sqlite3.connect(temp_db)
        rows = conn.execute(
            "SELECT tier FROM tier_attempts WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        conn.close()

        tiers = [r[0] for r in rows]
        assert tiers == ["T1", "T2"]


class TestRecordTierResult:
    """Test 3: record_tier_result updates attempt."""

    def test_updates_tier_attempt(self, telemetry, temp_db):
        """record_tier_result updates the matching tier_attempts row."""
        session_id = telemetry.record_submission_start("job-1", "greenhouse")
        now = datetime.utcnow().isoformat()
        telemetry.record_tier_attempt(session_id, "T1", now)

        telemetry.record_tier_result(
            session_id=session_id,
            tier="T1",
            success=True,
            duration_sec=12.5,
            tokens_used=1500,
        )

        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT success, duration_sec, tokens_used, error_type FROM tier_attempts WHERE session_id = ? AND tier = 'T1'",
            (session_id,),
        ).fetchone()
        conn.close()

        assert row[0] == 1  # success = True -> 1
        assert abs(row[1] - 12.5) < 0.01
        assert row[2] == 1500
        assert row[3] is None  # no error

    def test_records_error_type(self, telemetry, temp_db):
        """record_tier_result stores error_type when provided."""
        session_id = telemetry.record_submission_start("job-1", "workday")
        now = datetime.utcnow().isoformat()
        telemetry.record_tier_attempt(session_id, "T2", now)

        telemetry.record_tier_result(
            session_id=session_id,
            tier="T2",
            success=False,
            duration_sec=30.0,
            tokens_used=5000,
            error_type="CAPTCHA_TIMEOUT",
        )

        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT success, error_type FROM tier_attempts WHERE session_id = ? AND tier = 'T2'",
            (session_id,),
        ).fetchone()
        conn.close()

        assert row[0] == 0  # success = False -> 0
        assert row[1] == "CAPTCHA_TIMEOUT"


class TestRecordSubmissionEnd:
    """Test 4: record_submission_end completes session."""

    def test_updates_submission_row(self, telemetry, temp_db):
        """record_submission_end sets ended_at, success, total_duration_sec, tiers, final_tier."""
        session_id = telemetry.record_submission_start("job-1", "greenhouse")

        telemetry.record_submission_end(
            session_id=session_id,
            success=True,
            total_duration_sec=45.2,
            tiers_attempted=["T1"],
            final_tier="T1",
        )

        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT success, total_duration_sec, tiers_attempted, final_tier, ended_at FROM submission_telemetry WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        conn.close()

        assert row[0] == 1
        assert abs(row[1] - 45.2) < 0.01
        assert json.loads(row[2]) == ["T1"]
        assert row[3] == "T1"
        assert row[4] is not None  # ended_at set

    def test_failed_submission_with_fallback(self, telemetry, temp_db):
        """Failed submission records tiers attempted across fallbacks."""
        session_id = telemetry.record_submission_start("job-1", "lever")

        telemetry.record_submission_end(
            session_id=session_id,
            success=False,
            total_duration_sec=120.0,
            tiers_attempted=["T1", "T2", "T3"],
            final_tier="T3",
        )

        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT success, tiers_attempted, final_tier FROM submission_telemetry WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        conn.close()

        assert row[0] == 0
        assert json.loads(row[1]) == ["T1", "T2", "T3"]
        assert row[2] == "T3"


class TestGetMetrics:
    """Test 5: get_metrics returns correct aggregations."""

    def test_basic_metrics(self, telemetry):
        """get_metrics returns correct total_submissions, success_rate, avg_duration."""
        # Insert 3 submissions: 2 success, 1 fail
        s1 = telemetry.record_submission_start("job-1", "greenhouse")
        telemetry.record_tier_attempt(s1, "T1", datetime.utcnow().isoformat())
        telemetry.record_tier_result(s1, "T1", True, 10.0, 0)
        telemetry.record_submission_end(s1, True, 10.0, ["T1"], "T1")

        s2 = telemetry.record_submission_start("job-2", "lever")
        telemetry.record_tier_attempt(s2, "T1", datetime.utcnow().isoformat())
        telemetry.record_tier_result(s2, "T1", False, 20.0, 0, "SESSION_EXPIRED")
        telemetry.record_tier_attempt(s2, "T2", datetime.utcnow().isoformat())
        telemetry.record_tier_result(s2, "T2", True, 30.0, 2000)
        telemetry.record_submission_end(s2, True, 50.0, ["T1", "T2"], "T2")

        s3 = telemetry.record_submission_start("job-3", "ashby")
        telemetry.record_tier_attempt(s3, "T1", datetime.utcnow().isoformat())
        telemetry.record_tier_result(s3, "T1", False, 15.0, 0, "CAPTCHA_TIMEOUT")
        telemetry.record_submission_end(s3, False, 15.0, ["T1"], "T1")

        metrics = telemetry.get_metrics(since_hours=24.0)

        assert metrics["total_submissions"] == 3
        assert abs(metrics["success_rate"] - 2 / 3) < 0.01
        assert abs(metrics["avg_duration_sec"] - (10.0 + 50.0 + 15.0) / 3) < 0.01

    def test_tier_distribution(self, telemetry):
        """tier_distribution shows fraction of submissions that resolved at each tier."""
        # T1 resolves 2, T2 resolves 1, T3 resolves 0
        for i, (tier, _) in enumerate([("T1", True), ("T1", True), ("T2", True)]):
            s = telemetry.record_submission_start(f"job-{i}", "greenhouse")
            telemetry.record_tier_attempt(s, tier, datetime.utcnow().isoformat())
            telemetry.record_tier_result(s, tier, True, 10.0, 0)
            telemetry.record_submission_end(s, True, 10.0, [tier], tier)

        metrics = telemetry.get_metrics()
        dist = metrics["tier_distribution"]
        assert dist["T1"] == pytest.approx(2 / 3, abs=0.01)
        assert dist["T2"] == pytest.approx(1 / 3, abs=0.01)

    def test_token_costs(self, telemetry):
        """token_costs aggregates tokens per tier."""
        s1 = telemetry.record_submission_start("job-1", "greenhouse")
        telemetry.record_tier_attempt(s1, "T2", datetime.utcnow().isoformat())
        telemetry.record_tier_result(s1, "T2", True, 10.0, 5000)
        telemetry.record_submission_end(s1, True, 10.0, ["T2"], "T2")

        s2 = telemetry.record_submission_start("job-2", "lever")
        telemetry.record_tier_attempt(s2, "T2", datetime.utcnow().isoformat())
        telemetry.record_tier_result(s2, "T2", True, 10.0, 7500)
        telemetry.record_submission_end(s2, True, 10.0, ["T2"], "T2")

        metrics = telemetry.get_metrics()
        assert metrics["token_costs"]["T2"] == 12500

    def test_error_breakdown(self, telemetry):
        """error_breakdown counts errors by type."""
        for job_id, err in [("j1", "CAPTCHA_TIMEOUT"), ("j2", "CAPTCHA_TIMEOUT"), ("j3", "SESSION_EXPIRED")]:
            s = telemetry.record_submission_start(job_id, "greenhouse")
            telemetry.record_tier_attempt(s, "T1", datetime.utcnow().isoformat())
            telemetry.record_tier_result(s, "T1", False, 5.0, 0, err)
            telemetry.record_submission_end(s, False, 5.0, ["T1"], "T1")

        metrics = telemetry.get_metrics()
        assert metrics["error_breakdown"]["CAPTCHA_TIMEOUT"] == 2
        assert metrics["error_breakdown"]["SESSION_EXPIRED"] == 1


class TestMetricsMissingData:
    """Test 6: Metrics handle missing data gracefully."""

    def test_empty_db(self, telemetry):
        """get_metrics on empty DB returns zeros."""
        metrics = telemetry.get_metrics()
        assert metrics["total_submissions"] == 0
        assert metrics["success_rate"] == 0.0
        assert metrics["avg_duration_sec"] == 0.0
        assert metrics["tier_distribution"] == {}
        assert metrics["token_costs"] == {}
        assert metrics["error_breakdown"] == {}

    def test_incomplete_session(self, telemetry):
        """Sessions without ended_at are excluded from duration averages."""
        s = telemetry.record_submission_start("job-1", "greenhouse")
        # No record_submission_end called

        metrics = telemetry.get_metrics()
        # Session exists but incomplete: total_submissions counts only completed
        assert metrics["total_submissions"] == 0
        assert metrics["avg_duration_sec"] == 0.0

    def test_tier_without_result(self, telemetry):
        """Tier attempts without results are excluded from token costs."""
        s = telemetry.record_submission_start("job-1", "greenhouse")
        telemetry.record_tier_attempt(s, "T1", datetime.utcnow().isoformat())
        # No record_tier_result
        telemetry.record_submission_end(s, False, 5.0, ["T1"], "T1")

        metrics = telemetry.get_metrics()
        # Token costs should not include T1 since no result recorded
        assert metrics["token_costs"].get("T1", 0) == 0
