# tests/unit/test_agent_base.py
import pytest

from src.agents.base import BaseAgent
from src.agents.runtime import AgentRuntime
from src.core.events import EventType, reset_event_bus
from src.core.events.event_bus import Event, get_event_bus
from src.core.telemetry.agent_ledger import get_decisions


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    reset_event_bus()
    import src.core.telemetry.agent_ledger as ledger
    monkeypatch.setattr(ledger, "DEFAULT_DB_PATH", str(tmp_path / "a.db"))
    yield tmp_path
    reset_event_bus()


class RecorderAgent(BaseAgent):
    def __init__(self):
        super().__init__("recorder")
        self.seen = []
        self.handles = [EventType.JOB_DISCOVERED]

    def on_event(self, event):
        self.seen.append(event)


def test_decide_writes_ledger_and_publishes(isolated):
    agent = RecorderAgent()
    seen_events = []
    get_event_bus().subscribe(EventType.AGENT_DECISION_MADE, seen_events.append)
    decision = agent.decide("select_sources", "workday jobs -> workday crawler",
                            job_id="j1", metadata={"crawlers": ["workday"]})
    assert decision.agent_name == "recorder"
    assert len(get_decisions(job_id="j1")) == 1
    assert seen_events[0].payload["decision_type"] == "select_sources"


def test_runtime_start_stop_subscribes(isolated):
    agent = RecorderAgent()
    runtime = AgentRuntime([agent], bridge_sse=False)
    runtime.start()
    assert agent.running is True
    get_event_bus().publish(Event(event_type=EventType.JOB_DISCOVERED,
                                  source="test", subject_id="j9"))
    assert len(agent.seen) == 1
    runtime.stop()
    assert agent.running is False
    get_event_bus().publish(Event(event_type=EventType.JOB_DISCOVERED,
                                  source="test", subject_id="j10"))
    assert len(agent.seen) == 1  # unsubscribed cleanly, no leak


def test_runtime_double_start_is_idempotent(isolated):
    agent = RecorderAgent()
    runtime = AgentRuntime([agent], bridge_sse=False)
    runtime.start()
    runtime.start()
    get_event_bus().publish(Event(event_type=EventType.JOB_DISCOVERED,
                                  source="test"))
    assert len(agent.seen) == 1  # subscribed once, not twice
    runtime.stop()


def test_handler_error_is_contained(isolated):
    class Boom(BaseAgent):
        def __init__(self):
            super().__init__("boom")
            self.handles = [EventType.JOB_DISCOVERED]

        def on_event(self, event):
            raise RuntimeError("agent crashed")

    agent = Boom()
    runtime = AgentRuntime([agent], bridge_sse=False)
    runtime.start()
    # publish must not raise through the bus (P5a isolation contract)
    assert get_event_bus().publish(
        Event(event_type=EventType.JOB_DISCOVERED, source="test")) == 1
    runtime.stop()
