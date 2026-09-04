"""Unified SSE endpoint for factory visualization (task-5).

Merges all event types (state_sync, node_entry, node_exit, structured_error,
agent_update, heartbeat) into a single stream with Last-Event-ID reconnection.

Also hosts the factory control-plane REST endpoints (Gap 3):
- POST /api/v2/agents/{agent_id}/pause|resume
- POST /api/v2/jobs/{job_id}/retry|cancel
- POST /api/v2/zones/{zone_name}/pause
- POST /api/v2/discovery/scan
"""

import asyncio
import json
import logging
import queue as _queue_mod
from collections.abc import AsyncGenerator
from datetime import date, datetime
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.interface.api import subagent_state as _ss

logger = logging.getLogger("careergraph.api.factory")

router = APIRouter()

_HEARTBEAT_INTERVAL_S = 1.5


def _json_default(obj: Any) -> Any:
    """Serialize datetime/date to ISO strings for SSE JSON payloads."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return str(obj)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, default=_json_default)


async def _generate_heartbeat() -> Dict[str, Any]:
    """Build a heartbeat event matching the task-4 contract."""
    return {
        "type": "heartbeat",
        "server_unix_ms": int(datetime.utcnow().timestamp() * 1000),
        "throttle_level": "normal",
        "max_event_interval_ms": 5000,
        "drop_count": 0,
        "seq_no": _ss._state_sync_seq_no,
    }


@router.get("/api/v2/factory/stream")
async def factory_stream(
    request: Request,
    last_event_id: Optional[str] = Header(None),
    once: bool = Query(default=False, description="Emit single state_sync and close"),
) -> StreamingResponse:
    """Unified SSE stream for factory visualization.

    - Sends initial ``state_sync`` on connect (full snapshot via broadcast_state_sync).
    - Merges all event types from the shared subscriber bus.
    - Supports Last-Event-ID for reconnection replay.
    - SSE format: ``id: <seq_no>\\ndata: <json>\\n\\n``
    - ``?once=true`` emits initial state_sync and closes (for testing).
    """
    reconciling = last_event_id is not None and last_event_id != ""

    async def event_generator() -> AsyncGenerator[str, None]:
        # 1. Reconnection: replay missed events from ring buffer
        if last_event_id:
            try:
                missed = _ss.replay_from_event_id(last_event_id)
                for evt in missed:
                    evt_id = evt.get("id", 0)
                    yield f"id: {evt_id}\ndata: {_dumps(evt)}\n\n"
            except Exception as e:
                logger.warning(f"Replay failed: {e}")

        # 2. Send initial state_sync snapshot — full state via broadcast_state_sync
        try:
            initial_state_sync = await _ss.broadcast_state_sync(reconciling=reconciling)
        except Exception as e:
            logger.warning(f"broadcast_state_sync failed, sending minimal sync: {e}")
            initial_state_sync = {
                "type": "state_sync",
                "seq_no": _ss._state_sync_seq_no,
                "reconciling": reconciling,
                "pipeline_state": {},
                "agent_states": {},
                "job_queue": {},
            }
        seq = initial_state_sync.get("seq_no", 1)
        yield f"id: {seq}\ndata: {_dumps(initial_state_sync)}\n\n"

        if once:
            return

        # 3. Subscribe to live event bus
        try:
            q = _ss.subscribe_subagent_events(maxsize=200)
        except Exception as e:
            logger.error(f"Subscribe failed: {e}")
            return

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    # Non-blocking poll with short timeout. q.get raises queue.Empty
                    # when idle; asyncio.wait_for raises TimeoutError if the thread
                    # itself stalls. Treat both as "no event yet" -> heartbeat.
                    event = await asyncio.wait_for(
                        asyncio.to_thread(q.get, block=True, timeout=0.5),
                        timeout=1.0,
                    )
                    seq = event.get("seq_no", event.get("id", 0))
                    yield f"id: {seq}\ndata: {_dumps(event)}\n\n"
                except (asyncio.TimeoutError, _queue_mod.Empty):
                    # Timeout / idle — emit heartbeat
                    heartbeat = await _generate_heartbeat()
                    yield f"data: {_dumps(heartbeat)}\n\n"
        finally:
            try:
                _ss.unsubscribe_subagent_events(q)
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Factory control-plane endpoints (Gap 3)
# ─────────────────────────────────────────────────────────────────────────────

# In-memory zone pause set. Zones are pipeline-stage views from the frontend;
# we track them by lowercased name since no persistent zone model exists yet.
_PAUSED_ZONES: Set[str] = set()

# Last scan metadata (informational for panels polling state).
_LAST_SCAN: Dict[str, Any] = {
    "triggered_at": None,
    "triggered_by": None,
    "status": "idle",
}


def _job_repo():
    """Lazy-load JobRepository with configured db_path. Returns None on failure."""
    try:
        from src.core.config import get_settings
        from src.core.db.repository import JobRepository

        settings = get_settings()
        return JobRepository(settings.db_path)
    except Exception as e:
        logger.warning("JobRepository unavailable: %s", e)
        return None


@router.post("/api/v2/agents/{agent_id}/pause")
async def pause_agent(agent_id: str) -> JSONResponse:
    """Pause a subagent. Returns updated agent snapshot or 404 if unknown."""
    if not _ss.set_agent_paused(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    agent = _ss.SUBAGENTS_STATE.get(agent_id, {})
    return JSONResponse({
        "status": "paused",
        "agent_id": agent_id,
        "agent": dict(agent),
    })


@router.post("/api/v2/agents/{agent_id}/resume")
async def resume_agent(agent_id: str) -> JSONResponse:
    """Resume a paused agent. Returns updated agent snapshot or 404 if unknown."""
    if not _ss.set_agent_resumed(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    agent = _ss.SUBAGENTS_STATE.get(agent_id, {})
    return JSONResponse({
        "status": "resumed",
        "agent_id": agent_id,
        "agent": dict(agent),
    })


@router.post("/api/v2/jobs/{job_id}/retry")
async def retry_job(job_id: str) -> JSONResponse:
    """Re-queue a failed/rejected job by resetting its status to DISCOVERED.

    Uses JobRepository.update_status; returns 404 if job not found or repo unavailable.
    """
    repo = _job_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Job repository unavailable")
    existing = repo.get_job(job_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    try:
        from src.core.models import JobStatus

        ok = repo.update_status(job_id, JobStatus.DISCOVERED)
    except Exception as e:
        logger.warning("retry_job update_status failed: %s", e)
        ok = False
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to retry job '{job_id}'")
    _ss.log_agent_event(f"[Operator] 🔁 Job {job_id} re-queued for retry.", "INFO")
    return JSONResponse({
        "status": "retried",
        "job_id": job_id,
        "new_status": "discovered",
    })


@router.post("/api/v2/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> JSONResponse:
    """Cancel a job by marking it IGNORED. Returns 404 if not found."""
    repo = _job_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="Job repository unavailable")
    existing = repo.get_job(job_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    try:
        from src.core.models import JobStatus

        ok = repo.update_status(job_id, JobStatus.IGNORED)
    except Exception as e:
        logger.warning("cancel_job update_status failed: %s", e)
        ok = False
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to cancel job '{job_id}'")
    _ss.log_agent_event(f"[Operator] 🛑 Job {job_id} cancelled.", "INFO")
    return JSONResponse({
        "status": "cancelled",
        "job_id": job_id,
        "new_status": "ignored",
    })


@router.post("/api/v2/zones/{zone_name}/pause")
async def pause_zone(zone_name: str) -> JSONResponse:
    """Toggle a pipeline zone's paused state. Zones are identified by lowercase name."""
    key = zone_name.lower()
    if key in _PAUSED_ZONES:
        _PAUSED_ZONES.discard(key)
        paused = False
        msg = f"Zone '{zone_name}' resumed."
    else:
        _PAUSED_ZONES.add(key)
        paused = True
        msg = f"Zone '{zone_name}' paused."
    _ss.log_agent_event(f"[Operator] {'⏸️ ' if paused else '▶️ '}{msg}", "INFO")
    return JSONResponse({
        "status": "paused" if paused else "resumed",
        "zone": zone_name,
        "paused": paused,
    })


@router.post("/api/v2/discovery/scan")
async def trigger_discovery_scan() -> JSONResponse:
    """Trigger a discovery scan. Marks scout agents active briefly and logs the event.

    Note: this does NOT launch the full crawler pipeline — it only flips agent state
    and records the scan request. Wiring to the real discovery crawlers is a follow-up.
    """
    now_iso = datetime.utcnow().isoformat()
    _LAST_SCAN.update({"triggered_at": now_iso, "triggered_by": "api", "status": "running"})
    scout_keys = ["scout_falcon", "scout_atlas", "scout_titan", "scout_horizon", "scout_aegis"]
    awakenings = []
    for key in scout_keys:
        if key in _ss.SUBAGENTS_STATE:
            _ss.set_agent_active(
                key,
                "SCANNING",
                f"Manual scan triggered by operator at {now_iso}.",
                "Manual scan",
            )
            awakenings.append(key)
    _ss.log_agent_event(
        f"[Operator] 🛰️  Manual discovery scan triggered. Awakened {len(awakenings)} scouts.",
        "INFO",
    )
    _LAST_SCAN["status"] = "dispatched"
    return JSONResponse({
        "status": "dispatched",
        "triggered_at": now_iso,
        "agents_awakened": awakenings,
    })


@router.get("/api/v2/factory/scan_status")
async def get_scan_status() -> JSONResponse:
    """Return metadata about the most recent discovery scan trigger."""
    return JSONResponse(dict(_LAST_SCAN))


@router.get("/api/v2/factory/paused_zones")
async def get_paused_zones() -> JSONResponse:
    """Return the set of currently paused zone names."""
    return JSONResponse({"paused_zones": sorted(_PAUSED_ZONES)})
