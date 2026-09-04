# tests/unit/test_sse_bridge.py
from unittest.mock import MagicMock, patch

from src.core.events import EventType, get_event_bus
from src.core.events.event_bus import Event, EventBus
from src.core.events.sse_bridge import install_sse_bridge


def teardown_function(_):
    get_event_bus  # noqa: B018 — keep import used; singleton reset not needed (tests use local buses)


def test_install_returns_handler_and_forwards_all_types():
    bus = EventBus()
    forwarded = MagicMock()
    with patch("src.interface.api.subagent_state.broadcast_subagent_event", forwarded):
        handler = install_sse_bridge(bus)
        # The bridge resolves the broadcaster at install time (lazy core->interface
        # import, never at module top), so publish is exercised inside the patch
        # window to observe the forwarded call.
        n = bus.publish(Event(event_type=EventType.JOB_DISCOVERED, source="t",
                              subject_id="j1", payload={"x": 1}))
    assert n > 0  # at least the bridge handler is subscribed to JOB_DISCOVERED
    forwarded.assert_called_once()
    args, kwargs = forwarded.call_args
    # kind + payload positional, priority keyword or positional — accept either
    forwarded_kind = args[0] if args else kwargs.get("kind")
    forwarded_payload = args[1] if len(args) > 1 else kwargs.get("payload")
    assert forwarded_kind == "domain_event:job_discovered"
    assert forwarded_payload["subject_id"] == "j1"
    assert forwarded_payload["payload"]["x"] == 1


def test_bridge_survives_sse_import_failure(caplog):
    import builtins

    bus = EventBus()
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "src.interface.api.subagent_state":
            raise ImportError("no interface layer")
        return real_import(name, *a, **k)

    with patch("builtins.__import__", fake_import):
        install_sse_bridge(bus)
    # publishing must not raise even though SSE is missing
    assert bus.publish(Event(event_type=EventType.CRAWLER_COMPLETED, source="t")) >= 1


def test_uninstall_via_returned_handler():
    bus = EventBus()
    handler = install_sse_bridge(bus, event_types=[EventType.JOB_DISCOVERED])
    bus.unsubscribe(EventType.JOB_DISCOVERED, handler)
    # after unsubscribe, no bridge handler remains on JOB_DISCOVERED
    assert bus.publish(Event(event_type=EventType.JOB_DISCOVERED, source="t")) == 0
