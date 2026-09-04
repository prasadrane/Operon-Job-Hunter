# tests/integration/test_p5_agent_flow.py
"""Full P5 story, offline: orchestrator finds jobs -> application agent runs
pipeline (dispatcher mocked) -> ledger rows for every decision -> events on
the bus."""
import time
from unittest.mock import MagicMock

import pytest

from src.core.config import Settings
from src.core.events import EventType, reset_event_bus
from src.core.events.event_bus import get_event_bus
from src.core.models import JobPosting, JobStatus
from src.core.telemetry.agent_ledger import get_decisions


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    reset_event_bus()
    import src.core.telemetry.agent_ledger as ledger
    monkeypatch.setattr(ledger, "DEFAULT_DB_PATH", str(tmp_path / "e2e.db"))
    yield tmp_path
    reset_event_bus()


def _settings(**over):
    base = dict(min_fit_score=72.0, auto_submit_enabled=False)
    base.update(over)
    return Settings(_env_file=None, **base)


def test_discover_to_evaluated_to_gated_outreach(isolated, monkeypatch):
    # 1. orchestrator: fake scanner returns 1 job
    from src.agents.discovery_orchestrator import DiscoveryOrchestratorAgent
    job = JobPosting(id="e2e_j1", company="Acme", title="SWE",
                     url="https://boards.greenhouse.io/acme/jobs/1",
                     source="scanner", status=JobStatus.DISCOVERED)
    scanner = MagicMock()
    scanner.scan_all.return_value = [job]

    # 2. application agent: repo returns the JobPosting; dispatcher high fit
    from src.agents.application_agent import ApplicationAgent
    dispatcher = MagicMock()
    dispatcher.process_single_job.return_value = {
        "job_id": "e2e_j1", "status": "SUCCESS", "fit_score": 90.0,
        "tailored": True, "hitl_ready": True, "duration_sec": 0.1, "error": None}
    repo = MagicMock()
    repo.get_job.return_value = job

    evaluated = []
    get_event_bus().subscribe(EventType.JOB_EVALUATED, evaluated.append)

    orch = DiscoveryOrchestratorAgent(scanner=scanner)
    app_agent = ApplicationAgent(dispatcher=dispatcher, job_repo=repo, concurrency=1)
    orch.start()
    app_agent.start()
    summary = orch.run_once()
    assert summary["jobs_ingested"] == 1

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not evaluated:
        time.sleep(0.05)
    assert evaluated and evaluated[0].subject_id == "e2e_j1"
    assert evaluated[0].payload["fit_score"] == 90.0

    for agent in (orch, app_agent):
        agent.stop()
    app_agent.executor.shutdown(wait=True)

    # 4. the ledger holds the whole story
    kinds = {d["decision_type"] for d in get_decisions()}
    assert {"select_sources", "scan_complete", "pipeline_start", "proceed"} <= kinds
