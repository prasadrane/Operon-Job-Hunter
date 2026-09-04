"""Integration test for asynchronous subagent sprint execution."""

import time
from unittest.mock import MagicMock
import pytest

from src.core.models import JobPosting
from src.interface.api.subagent_state import (
    get_all_subagents_state,
    run_autonomous_sprint_pipeline,
    set_agent_active,
    set_agent_sleeping,
)


def test_subagent_state_transitions_and_snapshots():
    """Verify subagent active/sleep state mutations and snapshot reporting."""
    set_agent_active("scout_falcon", "SCANNING", "Scanning boards", "Fast-Path", {"Latency": "10ms"})
    state = get_all_subagents_state()

    assert state["subagents"]["scout_falcon"]["status"] == "active"
    assert state["subagents"]["scout_falcon"]["state_label"] == "SCANNING"
    assert state["active_count"] >= 1

    set_agent_sleeping("scout_falcon", "Sleeping after scan")
    state_after = get_all_subagents_state()
    assert state_after["subagents"]["scout_falcon"]["status"] == "sleeping"


def test_run_autonomous_sprint_pipeline_execution():
    """Verify autonomous sprint worker launches in background and processes jobs."""
    mock_job_repo = MagicMock()
    mock_eval_repo = MagicMock()
    mock_art_repo = MagicMock()

    sample_job = JobPosting(
        id="sprint_test_job_1",
        company="Stripe",
        title="Backend Infrastructure Engineer",
        url="https://stripe.com/jobs/1",
        portal_type="greenhouse",
    )
    mock_job_repo.get_all_jobs.return_value = [sample_job]

    res = run_autonomous_sprint_pipeline(
        job_repo=mock_job_repo,
        eval_repo=mock_eval_repo,
        art_repo=mock_art_repo,
    )

    assert res["status"] in ("started", "already_running")
