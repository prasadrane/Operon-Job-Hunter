"""Integration tests for SubmissionTelemetry.

Tests 7-8 from P3d Task 6 spec:
7. Integration: full telemetry flow
8. Integration: metrics query returns expected structure
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta

import pytest

from src.core.telemetry.submission_telemetry import SubmissionTelemetry


@pytest.fixture
def integration_db():
    """Create a temp DB for integration testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def telemetry(integration_db):
    """SubmissionTelemetry backed by integration DB."""
    return SubmissionTelemetry(db_path=integration_db)


class TestFullTelemetryFlow:
    """Test 7: full telemetry flow end-to-end."""

    def test_complete_submission_lifecycle(self, telemetry, integration_db):
        """Simulate full T1->T2->T3 fallback lifecycle and verify DB state."""
        # Start submission
        session_id = telemetry.record_submission_start("job-abc", "workday_agentic")
        assert session_id

        # T1 FastPath attempt - fails
        t1_start = datetime.utcnow().isoformat()
        telemetry.record_tier_attempt(session_id, "T1", t1_start)
        telemetry.record_tier_result(session_id, "T1", False, 8.0, 0, "SELECTOR_NOT_FOUND")

        # T2 Adapter attempt - fails
        t2_start = datetime.utcnow().isoformat()
        telemetry.record_tier_attempt(session_id, "T2", t2_start)
        telemetry.record_tier_result(session_id, "T2", False, 25.0, 3000, "CAPTCHA_TIMEOUT")

        # T3 WebSurfer attempt - success
        t3_start = datetime.utcnow().isoformat()
        telemetry.record_tier_attempt(session_id, "T3", t3_start)
        telemetry.record_tier_result(session_id, "T3", True, 60.0, 8000)

        # End
        telemetry.record_submission_end(
            session_id, True, 93.0, ["T1", "T2", "T3"], "T3"
        )

        # Verify DB state
        conn = sqlite3.connect(integration_db)
        conn.row_factory = sqlite3.Row

        sub_row = conn.execute(
            "SELECT * FROM submission_telemetry WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        assert sub_row["job_id"] == "job-abc"
        assert sub_row["portal_type"] == "workday_agentic"
        assert sub_row["success"] == 1
        assert abs(sub_row["total_duration_sec"] - 93.0) < 0.01
        assert json.loads(sub_row["tiers_attempted"]) == ["T1", "T2", "T3"]
        assert sub_row["final_tier"] == "T3"

        tier_rows = conn.execute(
            "SELECT * FROM tier_attempts WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        assert len(tier_rows) == 3
        assert tier_rows[0]["tier"] == "T1"
        assert tier_rows[0]["success"] == 0
        assert tier_rows[0]["error_type"] == "SELECTOR_NOT_FOUND"
        assert tier_rows[1]["tier"] == "T2"
        assert tier_rows[1]["tokens_used"] == 3000
        assert tier_rows[2]["tier"] == "T3"
        assert tier_rows[2]["success"] == 1

        conn.close()

    def test_multiple_submissions_aggregated(self, telemetry):
        """Multiple submissions produce correct aggregate metrics."""
        # 5 submissions: 3 success, 2 fail
        for i in range(5):
            s = telemetry.record_submission_start(f"job-{i}", "greenhouse")
            telemetry.record_tier_attempt(s, "T1", datetime.utcnow().isoformat())
            if i < 3:
                telemetry.record_tier_result(s, "T1", True, 10.0 + i, 0)
                telemetry.record_submission_end(s, True, 10.0 + i, ["T1"], "T1")
            else:
                telemetry.record_tier_result(s, "T1", False, 5.0, 0, "SESSION_EXPIRED")
                telemetry.record_submission_end(s, False, 5.0, ["T1"], "T1")

        metrics = telemetry.get_metrics()
        assert metrics["total_submissions"] == 5
        assert abs(metrics["success_rate"] - 0.6) < 0.01


class TestMetricsQueryStructure:
    """Test 8: metrics query returns expected structure."""

    def test_metrics_structure_complete(self, telemetry):
        """get_metrics returns all expected keys with correct types."""
        metrics = telemetry.get_metrics()

        expected_keys = {
            "total_submissions",
            "success_rate",
            "avg_duration_sec",
            "tier_distribution",
            "token_costs",
            "error_breakdown",
        }
        assert set(metrics.keys()) == expected_keys
        assert isinstance(metrics["total_submissions"], int)
        assert isinstance(metrics["success_rate"], float)
        assert isinstance(metrics["avg_duration_sec"], float)
        assert isinstance(metrics["tier_distribution"], dict)
        assert isinstance(metrics["token_costs"], dict)
        assert isinstance(metrics["error_breakdown"], dict)

    def test_metrics_with_since_filter(self, telemetry):
        """get_metrics respects since_hours parameter."""
        # Add an old submission (mock by direct DB insert)
        old_session = telemetry.record_submission_start("job-old", "greenhouse")
        telemetry.record_tier_attempt(old_session, "T1", datetime.utcnow().isoformat())
        telemetry.record_tier_result(old_session, "T1", True, 10.0, 0)
        telemetry.record_submission_end(old_session, True, 10.0, ["T1"], "T1")

        # Manually backdate the started_at
        conn = sqlite3.connect(telemetry.db_path)
        old_time = (datetime.utcnow() - timedelta(hours=48)).isoformat()
        conn.execute(
            "UPDATE submission_telemetry SET started_at = ? WHERE session_id = ?",
            (old_time, old_session),
        )
        conn.commit()
        conn.close()

        # Add recent submission
        new_session = telemetry.record_submission_start("job-new", "lever")
        telemetry.record_tier_attempt(new_session, "T1", datetime.utcnow().isoformat())
        telemetry.record_tier_result(new_session, "T1", True, 20.0, 0)
        telemetry.record_submission_end(new_session, True, 20.0, ["T1"], "T1")

        # Query last 24h: should only see the new one
        metrics_24h = telemetry.get_metrics(since_hours=24.0)
        assert metrics_24h["total_submissions"] == 1

        # Query last 72h: should see both
        metrics_72h = telemetry.get_metrics(since_hours=72.0)
        assert metrics_72h["total_submissions"] == 2
