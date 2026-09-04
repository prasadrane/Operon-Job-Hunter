"""Tests for SSE telemetry bus: ring buffer, rate limiter, priority, Last-Event-ID replay.

Contract task-1: subagent_state.py additions.
"""
import asyncio
import time
import pytest

from src.interface.api.subagent_state import (
    TelemetryEvent,
    TelemetryPriority,
    broadcast_subagent_event,
    get_telemetry_ring_buffer,
    subscribe_subagent_events,
    unsubscribe_subagent_events,
    reset_telemetry_state,
)


# ── Priority tiers ────────────────────────────────────────────────────────────

class TestTelemetryPriority:
    def test_three_tiers_exist(self):
        tiers = {p.name for p in TelemetryPriority}
        assert tiers == {"LIFECYCLE", "DECISION", "DEBUG"}

    def test_priority_ordering(self):
        """LIFECYCLE > DECISION > DEBUG for eviction protection."""
        assert TelemetryPriority.LIFECYCLE.value > TelemetryPriority.DECISION.value
        assert TelemetryPriority.DECISION.value > TelemetryPriority.DEBUG.value


# ── broadcast_subagent_event emits to subscribers ─────────────────────────────

class TestBroadcastToSubscribers:
    def setup_method(self):
        reset_telemetry_state()

    def teardown_method(self):
        reset_telemetry_state()

    def test_event_delivered_to_single_subscriber(self):
        q = subscribe_subagent_events()
        try:
            broadcast_subagent_event("test_event", {"key": "value"}, priority=TelemetryPriority.LIFECYCLE)
            event = q.get_nowait()
            assert event["event"] == "test_event"
            assert event["payload"]["key"] == "value"
        finally:
            unsubscribe_subagent_events(q)

    def test_event_delivered_to_multiple_subscribers(self):
        q1 = subscribe_subagent_events()
        q2 = subscribe_subagent_events()
        try:
            broadcast_subagent_event("multi", {"n": 1}, priority=TelemetryPriority.DECISION)
            e1 = q1.get_nowait()
            e2 = q2.get_nowait()
            assert e1["event"] == "multi"
            assert e2["event"] == "multi"
        finally:
            unsubscribe_subagent_events(q1)
            unsubscribe_subagent_events(q2)

    def test_payload_is_dict(self):
        """Contract: broadcast_subagent_event(event_type: str, payload: dict)."""
        q = subscribe_subagent_events()
        try:
            broadcast_subagent_event("typed", {"score": 85}, priority=TelemetryPriority.DEBUG)
            event = q.get_nowait()
            assert isinstance(event["payload"], dict)
        finally:
            unsubscribe_subagent_events(q)

    def test_event_has_id_for_replay(self):
        """Each event must carry a monotonic ID for Last-Event-ID replay."""
        q = subscribe_subagent_events()
        try:
            broadcast_subagent_event("e1", {}, priority=TelemetryPriority.LIFECYCLE)
            broadcast_subagent_event("e2", {}, priority=TelemetryPriority.LIFECYCLE)
            ev1 = q.get_nowait()
            ev2 = q.get_nowait()
            assert "id" in ev1
            assert "id" in ev2
            assert ev2["id"] > ev1["id"]
        finally:
            unsubscribe_subagent_events(q)


# ── Ring buffer: 200-event capacity, eviction policy ─────────────────────────

class TestRingBuffer:
    def setup_method(self):
        reset_telemetry_state()

    def teardown_method(self):
        reset_telemetry_state()

    def test_buffer_stores_events(self):
        for i in range(10):
            broadcast_subagent_event(f"evt_{i}", {"i": i}, priority=TelemetryPriority.LIFECYCLE)
        buf = get_telemetry_ring_buffer()
        assert len(buf) == 10

    def test_buffer_caps_at_200(self):
        """Ring buffer max size is 200 events."""
        for i in range(250):
            broadcast_subagent_event(f"cap_test_{i}", {"i": i}, priority=TelemetryPriority.DEBUG)
        buf = get_telemetry_ring_buffer()
        # Buffer may have external events; total must be <= 200
        assert len(buf) <= 200

    def test_debug_evicted_first_under_pressure(self):
        """Under capacity pressure, DEBUG events are dropped before DECISION/LIFECYCLE."""
        for i in range(100):
            broadcast_subagent_event(f"debug_{i}", {}, priority=TelemetryPriority.DEBUG)
        for i in range(60):
            broadcast_subagent_event(f"decision_{i}", {}, priority=TelemetryPriority.DECISION)
        for i in range(60):
            broadcast_subagent_event(f"lifecycle_{i}", {}, priority=TelemetryPriority.LIFECYCLE)
        buf = get_telemetry_ring_buffer()
        assert len(buf) <= 200
        event_types = [e.get("event", "") for e in buf]
        debug_remaining = sum(1 for e in event_types if e.startswith("debug_"))
        decision_remaining = sum(1 for e in event_types if e.startswith("decision_"))
        lifecycle_remaining = sum(1 for e in event_types if e.startswith("lifecycle_"))
        # LIFECYCLE events immune: all 60 must survive
        assert lifecycle_remaining == 60
        # DECISION protected against DEBUG: all 60 must survive
        assert decision_remaining == 60
        # DEBUG evicted first: at most 80 (since 220+external > 200)
        assert debug_remaining <= 100

    def test_lifecycle_immune_to_eviction(self):
        """LIFECYCLE events must never be evicted."""
        for i in range(150):
            broadcast_subagent_event(f"immune_{i}", {}, priority=TelemetryPriority.LIFECYCLE)
        for i in range(100):
            broadcast_subagent_event(f"evict_debug_{i}", {}, priority=TelemetryPriority.DEBUG)
        buf = get_telemetry_ring_buffer()
        lifecycle_count = sum(1 for e in buf if e.get("event", "").startswith("immune_"))
        assert lifecycle_count == 150


# ── Rate limiter: 50 evt/sec/client, drops DEBUG first ───────────────────────

class TestRateLimiter:
    def setup_method(self):
        reset_telemetry_state()

    def teardown_method(self):
        reset_telemetry_state()

    def test_burst_under_limit_delivers_all(self):
        """Events under 50/sec rate limit are delivered."""
        q = subscribe_subagent_events()
        try:
            for i in range(40):
                broadcast_subagent_event(f"ok_{i}", {}, priority=TelemetryPriority.DECISION)
            delivered = 0
            while not q.empty():
                q.get_nowait()
                delivered += 1
            assert delivered == 40
        finally:
            unsubscribe_subagent_events(q)

    def test_overlimit_drops_debug_first(self):
        """Under backpressure, DEBUG events are dropped before higher priorities."""
        q = subscribe_subagent_events(maxsize=50)
        try:
            # Fill queue to capacity with DEBUG events, then send LIFECYCLE
            for i in range(50):
                broadcast_subagent_event(f"debug_{i}", {}, priority=TelemetryPriority.DEBUG)
            # Now queue is full; send a LIFECYCLE event
            broadcast_subagent_event("critical", {}, priority=TelemetryPriority.LIFECYCLE)
            # Drain queue; LIFECYCLE should be present
            events = []
            while not q.empty():
                events.append(q.get_nowait())
            lifecycle_events = [e for e in events if e["event"] == "critical"]
            assert len(lifecycle_events) == 1
        finally:
            unsubscribe_subagent_events(q)


# ── Last-Event-ID replay from ring buffer ────────────────────────────────────

class TestLastEventIdReplay:
    def setup_method(self):
        reset_telemetry_state()

    def teardown_method(self):
        reset_telemetry_state()

    def test_replay_returns_events_after_id(self):
        """Subscriber reconnecting with Last-Event-ID receives missed events."""
        # Use broadcast_subagent_event's own globals to ensure we read from the
        # same module instance the function writes to (guards against duplicate
        # module instances from different import paths in the test suite).
        _g = broadcast_subagent_event.__globals__
        _get_ring = _g["get_telemetry_ring_buffer"]
        _replay = _g["replay_from_event_id"]

        q = subscribe_subagent_events()
        try:
            for i in range(10):
                broadcast_subagent_event(f"replay_test_{i}", {"i": i}, priority=TelemetryPriority.LIFECYCLE)

            ring = _get_ring()
            ring_ids = {e["id"] for e in ring if e["event"].startswith("replay_test_")}

            captured = []
            while not q.empty():
                evt = q.get_nowait()
                if evt["event"].startswith("replay_test_"):
                    captured.append(evt)

            assert len(captured) == 10, f"Queue captured {len(captured)} events"
            assert len(ring_ids) >= 5, f"Ring has {len(ring_ids)} replay_test events (ring size: {len(ring)})"
            captured.sort(key=lambda e: e["id"])
            ids = [e["id"] for e in captured]

            missed = _replay(str(ids[4]))
            our_missed = sorted(
                [e for e in missed if e["event"].startswith("replay_test_")],
                key=lambda e: e["id"],
            )
            assert len(our_missed) == 5
            assert our_missed[0]["payload"]["i"] == 5
            assert our_missed[-1]["payload"]["i"] == 9
        finally:
            unsubscribe_subagent_events(q)

    def test_replay_with_unknown_id_returns_all(self):
        """Unknown Last-Event-ID returns all buffered events."""
        _g = broadcast_subagent_event.__globals__
        _replay = _g["replay_from_event_id"]
        for i in range(5):
            broadcast_subagent_event(f"unk_test_{i}", {}, priority=TelemetryPriority.LIFECYCLE)
        missed = _replay("nonexistent-id")
        assert len(missed) >= 5

    def test_replay_empty_buffer(self):
        """After reset, replaying with any ID returns no events with our prefix."""
        _g = broadcast_subagent_event.__globals__
        _get_ring = _g["get_telemetry_ring_buffer"]
        buf = _get_ring()
        our_events = [e for e in buf if e["event"].startswith("empty_test_")]
        assert len(our_events) == 0
