"""Integration test for unified SSE stream endpoint."""

import json
import pytest
from httpx import AsyncClient, ASGITransport

from src.interface.api.routes import app

# Upper bound on data lines scanned for the wanted event. With Last-Event-ID
# the endpoint first replays the process-global telemetry ring (max
# _RING_BUFFER_MAX = 200 entries in src/interface/api/subagent_state.py), then
# yields the live ``state_sync`` snapshot. 250 = ring capacity + headroom, so
# the scan is order-robust no matter what earlier tests pushed into the ring.
_MAX_EVENTS_TO_SCAN = 250


def _first_event_of_type(sse_text: str, wanted_type: str) -> dict:
    """Return first parsed SSE ``data:`` event with top-level ``type == wanted_type``.

    Order-robust read loop over up to _MAX_EVENTS_TO_SCAN data lines:
    - JSON parse failure -> skip, continue;
    - non-dict or dict without a top-level ``type`` key -> skip, continue
      (replayed telemetry-ring envelopes have shape {id, event, payload,
      priority, timestamp} and never carry a top-level ``type``);
    - dict with a different ``type`` (e.g. ``heartbeat``) -> not a match, keep scanning.

    The live state_sync from ``broadcast_state_sync`` and heartbeats from
    ``_generate_heartbeat`` both carry ``type`` at the top level, so this
    discriminates them deterministically from ring-replay noise.
    Raises AssertionError if no matching event appears within the cap.
    """
    lines = sse_text.strip().split("\n")
    data_lines = [l for l in lines if l.startswith("data:")][: _MAX_EVENTS_TO_SCAN]
    assert data_lines, "Should receive at least one data event"

    for line in data_lines:
        try:
            event = json.loads(line[len("data:"):].strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or "type" not in event:
            continue
        if event["type"] == wanted_type:
            return event
    raise AssertionError(f"No {wanted_type!r} event found within {_MAX_EVENTS_TO_SCAN} data lines")


@pytest.mark.asyncio
async def test_factory_stream_connects():
    """Factory stream endpoint accepts SSE connection with Last-Event-ID."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Use ?once=true to get single event and close
        response = await client.get(
            "/api/v2/factory/stream",
            params={"once": True},
            headers={"Last-Event-ID": "0"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        # Scan past any replayed ring events for the live state_sync snapshot
        event = _first_event_of_type(response.text, "state_sync")
        assert "seq_no" in event
        assert event["reconciling"] is True  # Last-Event-ID was provided


@pytest.mark.asyncio
async def test_factory_stream_without_last_event_id():
    """Factory stream works without Last-Event-ID header (fresh connection)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v2/factory/stream", params={"once": True})
        assert response.status_code == 200

        event = _first_event_of_type(response.text, "state_sync")
        assert event["reconciling"] is False  # No Last-Event-ID


@pytest.mark.asyncio
async def test_factory_stream_sse_format():
    """Factory stream events use correct SSE format with id and data fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v2/factory/stream", params={"once": True})
        assert response.status_code == 200

        lines = response.text.strip().split("\n")
        # Should have id: and data: lines
        id_lines = [l for l in lines if l.startswith("id:")]
        data_lines = [l for l in lines if l.startswith("data:")]

        assert len(id_lines) >= 1, "SSE event must include id: field"
        assert len(data_lines) >= 1, "SSE event must include data: field"


@pytest.mark.asyncio
async def test_factory_stream_route_registered():
    """Factory stream route is registered in the app."""
    routes = [r.path for r in app.routes]
    assert "/api/v2/factory/stream" in routes
