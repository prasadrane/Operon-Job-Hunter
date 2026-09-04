# tests/unit/test_discovery_orchestrator.py
from unittest.mock import MagicMock

import pytest

from src.core.events import EventType, reset_event_bus
from src.core.events.event_bus import Event, get_event_bus


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    reset_event_bus()
    import src.core.telemetry.agent_ledger as ledger
    monkeypatch.setattr(ledger, "DEFAULT_DB_PATH", str(tmp_path / "o.db"))
    yield
    reset_event_bus()


def _fake_scanner(jobs):
    scanner = MagicMock()
    scanner.scan_all.return_value = jobs
    return scanner


def _posting(i=1):
    from src.core.models import JobPosting, JobStatus
    return JobPosting(id=f"j{i}", company=f"c{i}", title=f"t{i}",
                      url=f"https://x/{i}", source="scanner",
                      status=JobStatus.DISCOVERED)


def test_run_once_publishes_and_logs(isolated):
    from src.agents.discovery_orchestrator import DiscoveryOrchestratorAgent
    from src.core.telemetry.agent_ledger import get_decisions
    agent = DiscoveryOrchestratorAgent(scanner=_fake_scanner([_posting(1), _posting(2)]))
    discovered = []
    get_event_bus().subscribe(EventType.JOB_DISCOVERED, discovered.append)
    summary = agent.run_once()
    assert summary["jobs_ingested"] == 2
    assert [e.subject_id for e in discovered] == ["j1", "j2"]
    types = [d["decision_type"] for d in get_decisions()]
    assert "select_sources" in types and "scan_complete" in types


def test_on_event_crawler_failed_logs_decision(isolated):
    from src.agents.discovery_orchestrator import DiscoveryOrchestratorAgent
    from src.core.telemetry.agent_ledger import get_decisions
    agent = DiscoveryOrchestratorAgent(scanner=_fake_scanner([]))
    agent.on_event(Event(event_type=EventType.CRAWLER_FAILED, source="t",
                         payload={"error": "429", "query": "swe"}))
    rows = get_decisions()
    assert len(rows) == 1
    assert rows[0]["agent_name"] == "discovery_orchestrator"
    assert "429" in rows[0]["reasoning"]
