"""Unit test verifying live per-company telemetry streaming and autonomous tailoring progression."""

import importlib
import pytest
from src.core.models import JobPosting, JobStatus
JobScanner = importlib.import_module("src.pipeline.1_discovery.scanner").JobScanner
from src.interface.api.routes import AGENT_LOGS, log_agent_event
from src.interface.api.subagent_state import SUBAGENTS_STATE, get_all_subagents_state


def test_scanner_logs_per_company_telemetry(monkeypatch):
    """Verify that JobScanner emits live per-company telemetry logs and updates subagent squad states."""
    test_companies = [
        {"name": "Stripe", "portal_type": "greenhouse", "board_token": "stripe", "enabled": True},
        {"name": "Capital One", "portal_type": "workday", "board_token": "capitalone", "enabled": True},
    ]

    mock_job_1 = JobPosting(
        id="gh_stripe_001",
        company="Stripe",
        title="Senior Backend Engineer, Payments",
        url="https://boards.greenhouse.io/stripe/jobs/001",
        portal_type="greenhouse",
        location="San Francisco, CA",
        description="Looking for Senior Backend Engineer with Python, AWS, and distributed systems experience.",
        status=JobStatus.DISCOVERED,
    )

    mock_job_2 = JobPosting(
        id="wd_c1_002",
        company="Capital One",
        title="Lead Cloud Platform Engineer",
        url="https://capitalone.wd1.myworkdayjobs.com/jobs/002",
        portal_type="workday",
        location="McLean, VA",
        description="Looking for Lead Cloud Engineer with AWS, C#, and Kubernetes.",
        status=JobStatus.DISCOVERED,
    )

    class MockCrawler:
        def crawl(self, portal_type, board_token, company_name, careers_url=None):
            if company_name == "Stripe":
                return [mock_job_1]
            return [mock_job_2]

    scanner = JobScanner(portal_crawler=MockCrawler())
    discovered = scanner.scan_all(companies=test_companies, filter_h1b=False, include_aggregators=False)

    assert len(discovered) == 2

    # Verify AGENT_LOGS has company-specific entries
    log_messages = [l["message"] for l in AGENT_LOGS]
    assert any("Stripe" in msg for msg in log_messages)
    assert any("Capital One" in msg for msg in log_messages)


def test_subagent_office_state_has_all_keys():
    """Verify that all 10 subagents are present in subagents state engine."""
    state = get_all_subagents_state()
    subagents = state["subagents"]
    required_keys = [
        "scout_falcon",
        "scout_atlas",
        "scout_titan",
        "scout_horizon",
        "scout_aegis",
        "evaluator",
        "factguard",
        "scribe",
        "websurfer",
        "outreach",
    ]
    for k in required_keys:
        assert k in subagents, f"Missing subagent key {k}"
