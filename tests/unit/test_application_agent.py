import threading
import time
from unittest.mock import MagicMock

import pytest

from src.core.config import Settings
from src.core.events import EventType, reset_event_bus
from src.core.events.event_bus import Event, get_event_bus


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    reset_event_bus()
    import src.core.telemetry.agent_ledger as ledger
    monkeypatch.setattr(ledger, "DEFAULT_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr("src.agents.application_agent.get_settings",
                        lambda: Settings(_env_file=None, min_fit_score=72.0,
                                         auto_submit_enabled=False))
    yield
    reset_event_bus()


def _job(i="j1"):
    from src.core.models import JobPosting, JobStatus
    return JobPosting(id=i, company="Acme", title="SWE",
                      url=f"https://boards.greenhouse.io/a/jobs/{i}",
                      portal_type="greenhouse", status=JobStatus.DISCOVERED)


def _agent(dispatcher, job_repo=None):
    from src.agents.application_agent import ApplicationAgent
    return ApplicationAgent(dispatcher=dispatcher,
                            job_repo=job_repo or MagicMock(get_job=lambda jid: _job(jid)))


def _wait_for(predicate, timeout=2.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_discovered_job_runs_dispatcher_and_emits_evaluated(wired):
    dispatcher = MagicMock()
    dispatcher.process_single_job.return_value = {
        "job_id": "j1", "status": "SUCCESS", "fit_score": 88.0,
        "tailored": True, "hitl_ready": True, "duration_sec": 1.0, "error": None}
    seen = []
    get_event_bus().subscribe(EventType.JOB_EVALUATED, seen.append)
    agent = _agent(dispatcher)
    agent.on_event(Event(event_type=EventType.JOB_DISCOVERED,
                         source="t", subject_id="j1"))
    assert _wait_for(lambda: len(seen) == 1)
    assert seen[0].payload["fit_score"] == 88.0
    assert seen[0].payload["hitl_ready"] is True
    dispatcher.process_single_job.assert_called_once()
    called_job = dispatcher.process_single_job.call_args[0][0]
    assert called_job.id == "j1" and called_job.url.endswith("/j1")
    agent.executor.shutdown(wait=True)


def test_low_fit_holds(wired):
    from src.core.telemetry.agent_ledger import get_decisions
    dispatcher = MagicMock()
    dispatcher.process_single_job.return_value = {
        "job_id": "j2", "status": "REJECTED", "fit_score": 40.0,
        "tailored": False, "hitl_ready": False, "duration_sec": 0.5, "error": None}
    agent = _agent(dispatcher)
    agent.on_event(Event(event_type=EventType.JOB_DISCOVERED, source="t",
                         subject_id="j2"))
    assert _wait_for(lambda: any(d["decision_type"] == "hold"
                                 for d in get_decisions(job_id="j2")))
    agent.executor.shutdown(wait=True)


def test_dedupe_inflight(wired):
    started = threading.Event()
    release = threading.Event()

    def slow_run(job):
        started.set()
        release.wait(timeout=5)
        return {"job_id": job.id, "status": "SUCCESS", "fit_score": 90.0,
                "tailored": False, "hitl_ready": False, "duration_sec": 9.9,
                "error": None}

    pipeline = MagicMock()
    pipeline.process_single_job.side_effect = slow_run
    agent = _agent(pipeline)
    agent.on_event(Event(event_type=EventType.JOB_DISCOVERED, source="t", subject_id="j3"))
    assert started.wait(timeout=2)          # first event picked up by worker
    agent.on_event(Event(event_type=EventType.JOB_DISCOVERED, source="t", subject_id="j3"))
    assert pipeline.process_single_job.call_count == 1  # second dropped (in-flight)
    release.set()
    agent.executor.shutdown(wait=True)
