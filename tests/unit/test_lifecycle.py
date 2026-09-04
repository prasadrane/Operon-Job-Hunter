"""Unit tests for Stage 5: Lifecycle Monitoring, Follow-Up Cadence & Funnel Analytics."""

import importlib
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest

from src.core.models import (
    ApplicationRecord,
    CandidateProfile,
    JobPosting,
    JobStatus,
)
from src.core.db.repository import ApplicationRepository, JobRepository

fe_mod = importlib.import_module("src.pipeline.5_lifecycle.followup_engine")
CadenceConfig = fe_mod.CadenceConfig
FollowupEngine = fe_mod.FollowupEngine
FollowupItem = fe_mod.FollowupItem
UrgencyLevel = fe_mod.UrgencyLevel

fa_mod = importlib.import_module("src.pipeline.5_lifecycle.funnel_analytics")
FunnelAnalytics = fa_mod.FunnelAnalytics
FunnelMetrics = fa_mod.FunnelMetrics


@pytest.fixture
def db_path(tmp_path):
    """Fixture providing temporary sqlite database path."""
    return str(tmp_path / "test_lifecycle.db")


# ---------------------------------------------------------------------------
# Follow-Up Engine Unit Tests
# ---------------------------------------------------------------------------


def test_followup_date_calculation():
    """Test follow-up due date calculation with default and custom cadence."""
    engine = FollowupEngine(cadence_days=7)
    submit_date = datetime(2026, 8, 20, 10, 0, 0)
    due_date = engine.calculate_due_date(submit_date)
    assert due_date == datetime(2026, 8, 27, 10, 0, 0)

    # Custom days override
    custom_due = engine.calculate_due_date(submit_date, days=14)
    assert custom_due == datetime(2026, 9, 3, 10, 0, 0)


def test_followup_urgency_computation():
    """Test compute_urgency across different application statuses, days elapsed, and touches."""
    engine = FollowupEngine(cadence_days=7, max_followups=2)

    # 1. Fresh application: 3 days since applied -> waiting
    assert engine.compute_urgency("applied", days_since_app=3, followup_count=0) == UrgencyLevel.WAITING

    # 2. Applied 8 days ago, 0 followups -> overdue
    assert engine.compute_urgency("applied", days_since_app=8, followup_count=0) == UrgencyLevel.OVERDUE

    # 3. Applied 15 days ago, 1 followup done 2 days ago -> waiting
    assert engine.compute_urgency("applied", days_since_app=15, days_since_last_followup=2, followup_count=1) == UrgencyLevel.WAITING

    # 4. Applied 20 days ago, 1 followup done 8 days ago -> overdue
    assert engine.compute_urgency("applied", days_since_app=20, days_since_last_followup=8, followup_count=1) == UrgencyLevel.OVERDUE

    # 5. Applied 30 days ago, 2 followups already done -> cold
    assert engine.compute_urgency("applied", days_since_app=30, days_since_last_followup=10, followup_count=2) == UrgencyLevel.COLD

    # 6. Responded today (<1 day) -> urgent
    assert engine.compute_urgency("responded", days_since_app=0, followup_count=0) == UrgencyLevel.URGENT

    # 7. Responded 4 days ago without follow-up -> overdue
    assert engine.compute_urgency("responded", days_since_app=4, followup_count=0) == UrgencyLevel.OVERDUE

    # 8. Interview 2 days ago -> overdue for thank you / follow-up
    assert engine.compute_urgency("interviewing", days_since_app=2, followup_count=0) == UrgencyLevel.OVERDUE


def test_followup_engine_get_pending_followups(db_path):
    """Test retrieving pending followups from repository records with date math and ordering."""
    job_repo = JobRepository(db_path)
    app_repo = ApplicationRepository(db_path)

    base_time = datetime(2026, 8, 10, 12, 0, 0)
    current_time = datetime(2026, 8, 22, 12, 0, 0)  # 12 days later

    # App 1: Applied 12 days ago, 0 followups -> overdue
    job1 = JobPosting(id="job_1", company="Stripe", title="Staff Engineer", url="https://stripe.com/1")
    job_repo.insert_job(job1)
    app1 = ApplicationRecord(
        id="app_1",
        job_id="job_1",
        company="Stripe",
        title="Staff Engineer",
        status=JobStatus.APPLIED,
        applied_at=base_time,
        notes="Applied 2026-08-10. Contact: recruiter@stripe.com",
    )
    app_repo.insert_application(app1)

    # App 2: Applied 2 days ago -> waiting
    job2 = JobPosting(id="job_2", company="Netflix", title="Senior Engineer", url="https://netflix.com/2")
    job_repo.insert_job(job2)
    app2 = ApplicationRecord(
        id="app_2",
        job_id="job_2",
        company="Netflix",
        title="Senior Engineer",
        status=JobStatus.APPLIED,
        applied_at=datetime(2026, 8, 20, 12, 0, 0),
    )
    app_repo.insert_application(app2)

    # App 3: Rejected -> should not be in active pending followups
    job3 = JobPosting(id="job_3", company="Meta", title="ML Engineer", url="https://meta.com/3")
    job_repo.insert_job(job3)
    app3 = ApplicationRecord(
        id="app_3",
        job_id="job_3",
        company="Meta",
        title="ML Engineer",
        status=JobStatus.REJECTED,
        applied_at=base_time,
    )
    app_repo.insert_application(app3)

    engine = FollowupEngine(cadence_days=7, app_repo=app_repo)
    pending = engine.get_pending_followups(current_date=current_time)

    assert len(pending) == 2
    overdue_item = next(p for p in pending if p.application_id == "app_1")
    assert overdue_item.urgency == UrgencyLevel.OVERDUE
    assert overdue_item.days_since_applied == 12
    assert overdue_item.email_draft is not None
    assert overdue_item.linkedin_message is not None
    assert overdue_item.contact_email == "recruiter@stripe.com"

    # Filter overdue only
    overdue_only = engine.get_pending_followups(current_date=current_time, overdue_only=True)
    assert len(overdue_only) == 1
    assert overdue_only[0].application_id == "app_1"


def test_followup_draft_email_generation():
    """Test generating professional follow-up email drafts for first and second touch."""
    profile = CandidateProfile(first_name="Alex", last_name="Rivera", email="alex.rivera@example.com")
    engine = FollowupEngine(candidate_profile=profile)

    # Touch 1
    draft1 = engine.generate_email_draft(
        company="Capital One",
        title="Senior .NET Engineer",
        contact_name="Sarah Miller",
        followup_number=1,
    )
    assert "Sarah Miller" in draft1
    assert "Senior .NET Engineer" in draft1
    assert "Capital One" in draft1
    assert "Alex Rivera" in draft1
    assert "following up" in draft1.lower()

    # Touch 2 (no contact name -> generic greeting)
    draft2 = engine.generate_email_draft(
        company="Amazon",
        title="Software Development Engineer II",
        contact_name=None,
        followup_number=2,
    )
    assert "Hiring Team" in draft2 or "Recruiter" in draft2 or "Hiring Manager" in draft2
    assert "Amazon" in draft2
    assert "Software Development Engineer II" in draft2
    assert "Alex Rivera" in draft2


def test_followup_draft_linkedin_message_generation():
    """Test generating LinkedIn follow-up outreach constrained under 300 characters."""
    profile = CandidateProfile(first_name="Alex", last_name="Rivera")
    engine = FollowupEngine(candidate_profile=profile)

    msg = engine.generate_linkedin_message(
        company="Google",
        title="Staff Software Engineer",
        contact_name="Alex",
    )
    assert "Alex" in msg
    assert "Staff Software Engineer" in msg
    assert "Alex" in msg
    assert len(msg) <= 300


# ---------------------------------------------------------------------------
# Funnel Analytics Unit Tests
# ---------------------------------------------------------------------------


def test_funnel_analytics_metrics_calculation(db_path):
    """Test full conversion funnel calculations, latencies, and portal breakdowns."""
    job_repo = JobRepository(db_path)
    app_repo = ApplicationRepository(db_path)

    t0 = datetime(2026, 8, 1, 10, 0, 0)
    t_reply_fast = datetime(2026, 8, 3, 10, 0, 0)  # 2 days later
    t_reply_slow = datetime(2026, 8, 7, 10, 0, 0)  # 6 days later

    # 1. Greenhouse job & app -> Interviewing (2 days latency)
    j1 = JobPosting(id="j1", company="Company 1", title="Role 1", url="https://boards.greenhouse.io/c1/1", portal_type="greenhouse")
    job_repo.insert_job(j1)
    app_repo.insert_application(ApplicationRecord(
        id="a1", job_id="j1", company="Company 1", title="Role 1",
        status=JobStatus.INTERVIEWING, applied_at=t0, last_status_update=t_reply_fast,
    ))

    # 2. Greenhouse job & app -> Offer (6 days latency)
    j2 = JobPosting(id="j2", company="Company 2", title="Role 2", url="https://boards.greenhouse.io/c2/2", portal_type="greenhouse")
    job_repo.insert_job(j2)
    app_repo.insert_application(ApplicationRecord(
        id="a2", job_id="j2", company="Company 2", title="Role 2",
        status=JobStatus.OFFER, applied_at=t0, last_status_update=t_reply_slow,
    ))

    # 3. Lever job & app -> Rejected (4 days latency)
    t_reply_mid = datetime(2026, 8, 5, 10, 0, 0)
    j3 = JobPosting(id="j3", company="Company 3", title="Role 3", url="https://jobs.lever.co/c3/3", portal_type="lever")
    job_repo.insert_job(j3)
    app_repo.insert_application(ApplicationRecord(
        id="a3", job_id="j3", company="Company 3", title="Role 3",
        status=JobStatus.REJECTED, applied_at=t0, last_status_update=t_reply_mid,
    ))

    # 4. Workday job & app -> Applied (no response yet)
    j4 = JobPosting(id="j4", company="Company 4", title="Role 4", url="https://c4.myworkdayjobs.com/4", portal_type="workday")
    job_repo.insert_job(j4)
    app_repo.insert_application(ApplicationRecord(
        id="a4", job_id="j4", company="Company 4", title="Role 4",
        status=JobStatus.APPLIED, applied_at=t0,
    ))

    analytics = FunnelAnalytics(app_repo=app_repo, job_repo=job_repo)
    metrics = analytics.calculate_metrics()

    assert metrics.total_applied == 4
    assert metrics.total_active == 3  # applied, interviewing, offer
    assert metrics.total_interviewing == 1
    assert metrics.total_offers == 1
    assert metrics.total_rejections == 1

    # Interview Conversion Rate: 1 / 4 = 25.0%
    assert metrics.interview_rate_pct == 25.0
    # Offer Conversion Rate: 1 / 4 = 25.0%
    assert metrics.offer_rate_pct == 25.0
    # Rejection Rate: 1 / 4 = 25.0%
    assert metrics.rejection_rate_pct == 25.0

    # Latencies: responses on [2 days, 6 days, 4 days] -> mean = 4.0 days, median = 4.0 days
    assert metrics.avg_response_latency_days == 4.0
    assert metrics.median_response_latency_days == 4.0

    # Portal breakdown checks
    assert "greenhouse" in metrics.portal_breakdown
    assert metrics.portal_breakdown["greenhouse"]["total"] == 2
    assert metrics.portal_breakdown["greenhouse"]["interviewing"] == 1
    assert metrics.portal_breakdown["greenhouse"]["offers"] == 1

    assert "lever" in metrics.portal_breakdown
    assert metrics.portal_breakdown["lever"]["total"] == 1
    assert metrics.portal_breakdown["lever"]["rejections"] == 1


def test_funnel_analytics_zero_division_guard(db_path):
    """Test calculating metrics with 0 applications produces valid zeroed statistics without exceptions."""
    app_repo = ApplicationRepository(db_path)
    job_repo = JobRepository(db_path)

    analytics = FunnelAnalytics(app_repo=app_repo, job_repo=job_repo)
    metrics = analytics.calculate_metrics()

    assert metrics.total_applied == 0
    assert metrics.interview_rate_pct == 0.0
    assert metrics.offer_rate_pct == 0.0
    assert metrics.rejection_rate_pct == 0.0
    assert metrics.avg_response_latency_days == 0.0


def test_funnel_analytics_markdown_report_formatting(db_path):
    """Test generating a comprehensive markdown report table from FunnelMetrics."""
    metrics = FunnelMetrics(
        total_applied=10,
        total_active=6,
        total_acknowledged=2,
        total_interviewing=3,
        total_offers=1,
        total_rejections=4,
        interview_rate_pct=30.0,
        offer_rate_pct=10.0,
        rejection_rate_pct=40.0,
        avg_response_latency_days=3.5,
        median_response_latency_days=3.0,
        portal_breakdown={
            "greenhouse": {"total": 5, "interviewing": 2, "offers": 1, "rejections": 1, "conversion_rate_pct": 40.0},
            "lever": {"total": 3, "interviewing": 1, "offers": 0, "rejections": 2, "conversion_rate_pct": 33.3},
        },
        status_breakdown={"applied": 2, "acknowledged": 2, "interviewing": 3, "offer": 1, "rejected": 4},
    )

    analytics = FunnelAnalytics()
    report = analytics.generate_report_markdown(metrics)

    assert "# Application Funnel & Lifecycle Analytics" in report
    assert "30.0%" in report
    assert "3.5 days" in report
    assert "greenhouse" in report
    assert "lever" in report
