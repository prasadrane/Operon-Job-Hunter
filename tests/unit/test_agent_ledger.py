# tests/unit/test_agent_ledger.py
import pytest

from src.core.telemetry.agent_ledger import (
    AgentDecision, ensure_ledger_schema, get_decisions, log_agent_decision,
)


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "ledger.db")
    ensure_ledger_schema(path)
    return path


def test_decision_defaults_and_record():
    d = AgentDecision(agent_name="discovery_orchestrator",
                      decision_type="select_sources",
                      reasoning="greenhouse job -> greenhouse crawler",
                      job_id="j1", metadata={"crawlers": ["greenhouse"]})
    assert d.timestamp.endswith("+00:00")
    rec = d.to_record()
    assert rec["agent_name"] == "discovery_orchestrator"
    assert rec["metadata"] == {"crawlers": ["greenhouse"]}
    assert set(rec) == {"id", "agent_name", "decision_type", "reasoning",
                        "job_id", "metadata", "timestamp"}


def test_log_and_read_back(db):
    d = AgentDecision(agent_name="a", decision_type="t", reasoning="r", job_id="j9")
    did = log_agent_decision(d, db_path=db)
    rows = get_decisions(job_id="j9", db_path=db)
    assert len(rows) == 1
    assert rows[0]["id"] == did
    assert rows[0]["metadata"] == {}


def test_get_decisions_filters_and_order(db):
    for i in range(3):
        log_agent_decision(
            AgentDecision(agent_name="app_agent", decision_type="proceed",
                          reasoning=f"r{i}", job_id="jA"), db_path=db)
    log_agent_decision(
        AgentDecision(agent_name="net_agent", decision_type="connect",
                      reasoning="rn", job_id="jB"), db_path=db)
    assert len(get_decisions(agent_name="app_agent", db_path=db)) == 3
    assert len(get_decisions(db_path=db)) == 4
    newest = get_decisions(limit=1, db_path=db)
    assert len(newest) == 1 and newest[0]["agent_name"] == "net_agent"


def test_ensure_schema_is_idempotent(db):
    ensure_ledger_schema(db)  # second call must not raise
