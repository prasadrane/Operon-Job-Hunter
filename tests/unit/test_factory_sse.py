import pytest
from src.interface.api.subagent_state import broadcast_state_sync

@pytest.mark.asyncio
async def test_state_sync_event_structure():
    """state_sync event contains pipeline_state, agent_states, job_queue with monotonic seq_no"""
    event = await broadcast_state_sync()

    assert event["type"] == "state_sync"
    assert "seq_no" in event
    assert isinstance(event["seq_no"], int)
    assert "pipeline_state" in event
    assert "agent_states" in event
    assert "job_queue" in event
    assert "reconciling" in event
    assert isinstance(event["reconciling"], bool)

@pytest.mark.asyncio
async def test_state_sync_seq_no_monotonic():
    """seq_no increments monotonically"""
    event1 = await broadcast_state_sync()
    event2 = await broadcast_state_sync()

    assert event2["seq_no"] > event1["seq_no"]


def test_node_entry_exit_events():
    """Pipeline nodes emit node_entry and node_exit events with job_id, stage, timestamp"""
    from src.pipeline.state_machine import with_circuit_breaker
    from src.interface.api.subagent_state import get_telemetry_ring_buffer, reset_telemetry_state

    @with_circuit_breaker(timeout_seconds=5.0)
    def test_node(state):
        return {"current_stage": "evaluation"}

    # Clear recent events
    reset_telemetry_state()

    # Execute node
    state = {"job_id": "test123", "current_stage": "discovery"}
    result = test_node(state)

    # Check events emitted
    events = get_telemetry_ring_buffer()
    node_entry = next((e for e in events if e["event"] == "node_entry"), None)
    node_exit = next((e for e in events if e["event"] == "node_exit"), None)

    assert node_entry is not None, "node_entry event not emitted"
    assert node_entry["payload"]["job_id"] == "test123"
    assert node_entry["payload"]["node"] == "test_node"
    assert node_entry["payload"]["stage"] == "discovery"
    assert "timestamp" in node_entry["payload"]

    assert node_exit is not None, "node_exit event not emitted"
    assert node_exit["payload"]["job_id"] == "test123"
    assert node_exit["payload"]["stage"] == "evaluation"
    assert "timestamp" in node_exit["payload"]


def test_structured_error_event():
    """Pipeline errors emit structured_error with correlation_id, tier, stack trace"""
    from src.pipeline.state_machine import with_circuit_breaker
    from src.interface.api.subagent_state import get_telemetry_ring_buffer, reset_telemetry_state

    @with_circuit_breaker(timeout_seconds=5.0)
    def failing_node(state):
        raise TimeoutError("45s budget exceeded")

    reset_telemetry_state()

    state = {"job_id": "abc123", "current_stage": "evaluation"}

    result = failing_node(state)

    events = get_telemetry_ring_buffer()
    error_event = next((e for e in events if e["event"] == "structured_error"), None)

    assert error_event is not None, "structured_error event not emitted"
    assert "correlation_id" in error_event["payload"]
    assert error_event["payload"]["error_code"] == "ERR_TIMEOUT"
    assert error_event["payload"]["node"] == "failing_node"
    assert error_event["payload"]["job_id"] == "abc123"
    assert error_event["payload"]["tier"] == 1  # root cause
    assert "stack_trace" in error_event["payload"]
    assert "timestamp" in error_event["payload"]


@pytest.mark.asyncio
async def test_heartbeat_contract():
    """Heartbeat includes server_unix_ms, throttle_level, drop_count, seq_no"""
    from src.interface.api.routes_v2 import _heartbeat_loop

    heartbeat = await anext(_heartbeat_loop())

    assert heartbeat["type"] == "heartbeat"
    assert "server_unix_ms" in heartbeat
    assert isinstance(heartbeat["server_unix_ms"], int)
    assert "throttle_level" in heartbeat
    assert heartbeat["throttle_level"] in ["normal", "degraded"]
    assert "max_event_interval_ms" in heartbeat
    assert "drop_count" in heartbeat
    assert "seq_no" in heartbeat
