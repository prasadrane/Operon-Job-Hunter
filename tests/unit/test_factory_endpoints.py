"""Unit tests for Gap 3 factory control-plane endpoints.

Tests the following endpoints added to routes_factory.py:
- POST /api/v2/agents/{agent_id}/pause
- POST /api/v2/agents/{agent_id}/resume
- POST /api/v2/jobs/{job_id}/retry
- POST /api/v2/jobs/{job_id}/cancel
- POST /api/v2/zones/{zone_name}/pause
- POST /api/v2/discovery/scan
"""

import types
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.interface.api import routes_factory, subagent_state


@pytest.fixture()
def client():
    """Build a minimal FastAPI app mounting only the factory router."""
    app = FastAPI()
    app.include_router(routes_factory.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_zone_state():
    """Reset in-memory paused zones between tests."""
    routes_factory._PAUSED_ZONES.clear()
    yield
    routes_factory._PAUSED_ZONES.clear()


# ─── Agent pause / resume ───────────────────────────────────────────────────

def test_pause_agent_known(client):
    resp = client.post("/api/v2/agents/scout_falcon/pause")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "paused"
    assert data["agent_id"] == "scout_falcon"
    assert subagent_state.SUBAGENTS_STATE["scout_falcon"]["status"] == "paused"


def test_pause_agent_unknown_returns_404(client):
    resp = client.post("/api/v2/agents/nonexistent_agent/pause")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_resume_agent_after_pause(client):
    client.post("/api/v2/agents/evaluator/pause")
    assert subagent_state.SUBAGENTS_STATE["evaluator"]["status"] == "paused"
    resp = client.post("/api/v2/agents/evaluator/resume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resumed"
    assert subagent_state.SUBAGENTS_STATE["evaluator"]["status"] in ("active", "sleeping")


def test_resume_agent_unknown_returns_404(client):
    resp = client.post("/api/v2/agents/ghost_agent/resume")
    assert resp.status_code == 404


# ─── Job retry / cancel ─────────────────────────────────────────────────────

def _make_fake_job():
    return types.SimpleNamespace(id="job-123", status="failed", url="https://x")


def test_retry_job_success(client):
    fake_repo = types.SimpleNamespace(
        get_job=lambda jid: _make_fake_job() if jid == "job-123" else None,
        update_status=lambda jid, st: True,
    )
    with patch.object(routes_factory, "_job_repo", return_value=fake_repo):
        resp = client.post("/api/v2/jobs/job-123/retry")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "retried"
    assert data["job_id"] == "job-123"
    assert data["new_status"] == "discovered"


def test_retry_job_not_found(client):
    fake_repo = types.SimpleNamespace(
        get_job=lambda jid: None,
        update_status=lambda jid, st: False,
    )
    with patch.object(routes_factory, "_job_repo", return_value=fake_repo):
        resp = client.post("/api/v2/jobs/missing-job/retry")
    assert resp.status_code == 404


def test_cancel_job_success(client):
    fake_repo = types.SimpleNamespace(
        get_job=lambda jid: _make_fake_job(),
        update_status=lambda jid, st: True,
    )
    with patch.object(routes_factory, "_job_repo", return_value=fake_repo):
        resp = client.post("/api/v2/jobs/job-123/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"
    assert data["new_status"] == "ignored"


def test_cancel_job_repo_unavailable(client):
    with patch.object(routes_factory, "_job_repo", return_value=None):
        resp = client.post("/api/v2/jobs/job-123/cancel")
    assert resp.status_code == 503


def test_cancel_job_not_found(client):
    fake_repo = types.SimpleNamespace(
        get_job=lambda jid: None,
        update_status=lambda jid, st: False,
    )
    with patch.object(routes_factory, "_job_repo", return_value=fake_repo):
        resp = client.post("/api/v2/jobs/nope/cancel")
    assert resp.status_code == 404


# ─── Zone pause toggle ──────────────────────────────────────────────────────

def test_pause_zone_toggles(client):
    # First call: pause
    resp1 = client.post("/api/v2/zones/discovery/pause")
    assert resp1.status_code == 200
    d1 = resp1.json()
    assert d1["paused"] is True
    assert d1["status"] == "paused"
    assert "discovery" in routes_factory._PAUSED_ZONES

    # Second call: resume (toggle)
    resp2 = client.post("/api/v2/zones/discovery/pause")
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["paused"] is False
    assert d2["status"] == "resumed"
    assert "discovery" not in routes_factory._PAUSED_ZONES


def test_zone_names_case_insensitive(client):
    client.post("/api/v2/zones/Evaluation/pause")
    assert "evaluation" in routes_factory._PAUSED_ZONES


# ─── Discovery scan trigger ─────────────────────────────────────────────────

def test_trigger_discovery_scan(client):
    resp = client.post("/api/v2/discovery/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "dispatched"
    assert "triggered_at" in data
    assert isinstance(data["agents_awakened"], list)
    assert "scout_falcon" in data["agents_awakened"]


def test_scan_status_endpoint(client):
    # Pre-condition: trigger scan
    client.post("/api/v2/discovery/scan")
    resp = client.get("/api/v2/factory/scan_status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("running", "dispatched")
    assert data["triggered_at"] is not None


def test_paused_zones_endpoint(client):
    client.post("/api/v2/zones/tailoring/pause")
    resp = client.get("/api/v2/factory/paused_zones")
    assert resp.status_code == 200
    data = resp.json()
    assert "tailoring" in data["paused_zones"]
