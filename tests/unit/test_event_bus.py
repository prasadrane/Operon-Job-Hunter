# tests/unit/test_event_bus.py
import pytest

from src.core.events.event_bus import Event, EventBus, get_event_bus, reset_event_bus
from src.core.events.event_types import EventType


def teardown_function(_):
    reset_event_bus()


def test_event_type_values_are_snake_case():
    assert EventType.JOB_DISCOVERED == "job_discovered"
    assert EventType.APPLICATION_SUBMITTED == "application_submitted"
    assert EventType.AGENT_DECISION_MADE == "agent_decision_made"


def test_event_creation_defaults():
    event = Event(event_type=EventType.JOB_DISCOVERED, source="scanner",
                  subject_id="job_123", payload={"title": "Engineer"})
    assert event.payload["title"] == "Engineer"
    assert event.timestamp.endswith("+00:00")
    d = event.to_dict()
    assert d["event_type"] == "job_discovered"
    assert d["subject_id"] == "job_123"
    assert d["source"] == "scanner"


def test_publish_calls_subscriber_once():
    bus = EventBus()
    seen = []
    handler = seen.append
    bus.subscribe(EventType.JOB_DISCOVERED, handler)
    event = Event(event_type=EventType.JOB_DISCOVERED, source="test")
    n = bus.publish(event)
    assert n == 1
    assert seen == [event]


def test_multiple_subscribers_all_called():
    bus = EventBus()
    calls = []
    bus.subscribe(EventType.JOB_DISCOVERED, lambda e: calls.append("a"))
    bus.subscribe(EventType.JOB_DISCOVERED, lambda e: calls.append("b"))
    bus.publish(Event(event_type=EventType.JOB_DISCOVERED, source="test"))
    assert calls == ["a", "b"]


def test_handler_exception_does_not_stop_others_or_raise():
    bus = EventBus()
    calls = []

    def boom(event):
        raise ValueError("handler failed")

    bus.subscribe(EventType.JOB_DISCOVERED, boom)
    bus.subscribe(EventType.JOB_DISCOVERED, lambda e: calls.append("ok"))
    n = bus.publish(Event(event_type=EventType.JOB_DISCOVERED, source="test"))
    assert calls == ["ok"]
    assert n == 2  # both invoked; one failed internally


def test_unsubscribe_removes_only_that_handler():
    bus = EventBus()
    calls = []
    a = lambda e: calls.append("a")
    b = lambda e: calls.append("b")
    bus.subscribe(EventType.JOB_DISCOVERED, a)
    bus.subscribe(EventType.JOB_DISCOVERED, b)
    bus.unsubscribe(EventType.JOB_DISCOVERED, a)
    bus.publish(Event(event_type=EventType.JOB_DISCOVERED, source="test"))
    assert calls == ["b"]


def test_global_bus_singleton():
    first = get_event_bus()
    assert get_event_bus() is first
    reset_event_bus()
    assert get_event_bus() is not first
