"""Unit tests for OARadar and FollowupEngine cadence automation."""

import importlib
from datetime import datetime, timedelta
import pytest

oa_mod = importlib.import_module("src.pipeline.5_lifecycle.oa_radar")
OARadar = oa_mod.OARadar
OADetectionResult = oa_mod.OADetectionResult

followup_mod = importlib.import_module("src.pipeline.5_lifecycle.followup_engine")
FollowupEngine = followup_mod.FollowupEngine
ApplicationRecord = followup_mod.ApplicationRecord


def test_oa_radar_detection_and_platform_extraction():
    """Verify OARadar parses assessment platform, company, and deadline from email content."""
    radar = OARadar()
    email_text = """
    Hi Alex,
    Thank you for applying to the Staff Backend Engineer position at Stripe.
    Please complete your HackerRank Technical Assessment within 5 days.
    Assessment Link: https://www.hackerrank.com/tests/abc123stripe
    """
    subject = "Stripe Online Assessment Invitation"
    
    result = radar.scan_email(subject=subject, body=email_text, sender="recruiting@stripe.com")
    assert result.is_oa is True
    assert result.platform.lower() == "hackerrank"
    assert result.company.lower() == "stripe"
    assert result.test_link == "https://www.hackerrank.com/tests/abc123stripe"


def test_oa_radar_codesignal_detection():
    """Verify OARadar detects CodeSignal assessments accurately."""
    radar = OARadar()
    email_text = "Please take your CodeSignal General Coding Assessment for Databricks."
    subject = "Databricks - CodeSignal Assessment"

    result = radar.scan_email(subject=subject, body=email_text, sender="databricks@codesignal.com")
    assert result.is_oa is True
    assert result.platform.lower() == "codesignal"
    assert result.company.lower() == "databricks"


def test_oa_radar_triggers_study_guide_compilation():
    """Verify OARadar compiles a tailored study guide bundle upon detecting an assessment."""
    radar = OARadar()
    result = OADetectionResult(
        is_oa=True,
        platform="HackerRank",
        company="Stripe",
        role="Staff Backend Engineer",
        test_link="https://hackerrank.com/test",
    )

    guide = radar.generate_prep_guide(result)
    assert guide is not None
    assert "Stripe" in guide["title"]
    assert "HackerRank" in guide["content"]
    assert len(guide["recommended_topics"]) > 0


def test_followup_cadence_schedule_evaluation():
    """Verify FollowupEngine accurately prioritizes day 5 and day 10 follow-ups."""
    engine = FollowupEngine()
    now = datetime.utcnow()

    # Application submitted 6 days ago -> Overdue for first touch
    app1 = ApplicationRecord(
        id="app_001",
        job_id="job_001",
        company="Stripe",
        title="Staff Engineer",
        status="applied",
        applied_at=now - timedelta(days=6),
    )

    # Application submitted 1 day ago -> Waiting
    app2 = ApplicationRecord(
        id="app_002",
        job_id="job_002",
        company="Databricks",
        title="Backend Engineer",
        status="applied",
        applied_at=now - timedelta(days=1),
    )

    items = engine.get_pending_followups([app1, app2], current_date=now)
    assert len(items) == 2
    assert items[0].company == "Stripe"
    assert items[0].urgency.value == "overdue"
    assert items[1].company == "Databricks"
    assert items[1].urgency.value == "waiting"
