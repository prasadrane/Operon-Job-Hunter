"""Unit tests for FastAPI API v2 routes in Mission Control 2.0."""

import pytest
from fastapi.testclient import TestClient

from src.interface.api.routes_v2 import app_v2

client = TestClient(app_v2)


def test_api_v2_graph_nodes_d3_serialization():
    """Verify /api/v2/graph/nodes returns D3 node-link serialized graph data."""
    response = client.get("/api/v2/graph/nodes")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "links" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["links"], list)
    assert len(data["nodes"]) > 0
    
    # Verify node structure
    first_node = data["nodes"][0]
    assert "id" in first_node
    assert "type" in first_node

    # Verify link structure if links exist
    if data["links"]:
        first_link = data["links"][0]
        assert "source" in first_link
        assert "target" in first_link


def test_api_v2_graph_communities_and_causal_paths():
    """Verify /api/v2/graph/communities and /api/v2/graph/causal_paths endpoints."""
    # 1. Communities
    resp_comm = client.get("/api/v2/graph/communities")
    assert resp_comm.status_code == 200
    comm_data = resp_comm.json()
    assert isinstance(comm_data, list)
    assert len(comm_data) > 0
    assert "title" in comm_data[0]
    assert "summary" in comm_data[0]

    # 2. Causal Paths
    resp_paths = client.get("/api/v2/graph/causal_paths?query=Kafka%20streaming%20uptime")
    assert resp_paths.status_code == 200
    paths_data = resp_paths.json()
    assert isinstance(paths_data, list)
    if paths_data:
        assert "reasoning_chain" in paths_data[0]

    # 3. Tri-Hybrid RRF
    resp_rrf = client.get("/api/v2/graph/rrf?query=AWS%20cloud%20modernization")
    assert resp_rrf.status_code == 200
    rrf_data = resp_rrf.json()
    assert isinstance(rrf_data, list)
    assert len(rrf_data) > 0
    assert "rrf_score" in rrf_data[0]

    # 4. Gap Analysis
    resp_gap = client.get("/api/v2/graph/gap_analysis?skills=Kafka,RabbitMQ,Rust")
    assert resp_gap.status_code == 200
    gap_data = resp_gap.json()
    assert "direct_matches" in gap_data
    assert "transferable_bridges" in gap_data

    # 5. Longitudinal Competencies
    resp_long = client.get("/api/v2/graph/longitudinal")
    assert resp_long.status_code == 200
    long_data = resp_long.json()
    assert isinstance(long_data, list)
    if long_data:
        assert "domain" in long_data[0]

    # 6. Interview Prep Packet
    resp_prep = client.get("/api/v2/graph/interview_prep?skills=Kafka,AWS,Dynatrace")
    assert resp_prep.status_code == 200
    prep_data = resp_prep.json()
    assert isinstance(prep_data, list)
    if prep_data:
        assert "question" in prep_data[0]
        assert "model_answer" in prep_data[0]




def test_api_v2_telemetry_stats():
    """Verify /api/v2/telemetry/stats returns key operational metrics."""
    response = client.get("/api/v2/telemetry/stats")
    assert response.status_code == 200
    data = response.json()

    # Verify presence of metrics (total applications, daily cap, avg cost, p95 latency)
    assert "total_applications_today" in data or "total_applications" in data
    assert "daily_cap" in data or "daily_rate_limit_cap" in data
    assert "average_cost_per_job_usd" in data or "avg_cost" in data
    assert "p95_latency_seconds" in data or "p95_latency" in data

    # Verify metric value types
    total_apps = data.get("total_applications_today", data.get("total_applications"))
    assert isinstance(total_apps, (int, float))
    daily_cap = data.get("daily_cap", data.get("daily_rate_limit_cap"))
    assert isinstance(daily_cap, (int, float))
    avg_cost = data.get("average_cost_per_job_usd", data.get("avg_cost"))
    assert isinstance(avg_cost, (int, float))
    p95_lat = data.get("p95_latency_seconds", data.get("p95_latency"))
    assert isinstance(p95_lat, (int, float))


def test_api_v2_telemetry_stream():
    """Verify /api/v2/telemetry/stream returns Server-Sent Events (text/event-stream)."""
    response = client.get("/api/v2/telemetry/stream?once=true")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "data:" in response.text


def test_api_v2_telemetry_spans():
    """Verify /api/v2/telemetry/spans returns audit spans list."""
    response = client.get("/api/v2/telemetry/spans")
    assert response.status_code == 200
    data = response.json()
    assert "spans" in data
    assert isinstance(data["spans"], list)


def test_api_v2_live_dag():
    """Verify /api/v2/pipeline/live_dag returns pipeline stages status."""
    response = client.get("/api/v2/pipeline/live_dag")
    assert response.status_code == 200
    data = response.json()
    assert "stages" in data
    assert isinstance(data["stages"], list)
    assert len(data["stages"]) >= 4


def test_api_v2_health():
    """Verify /api/v2/health endpoint returns 200 OK with service info."""
    response = client.get("/api/v2/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "healthy"
    assert "version" in data


def test_api_v2_agentic_guardrails_telemetry():
    """Verify /api/v2/telemetry/agentic_guardrails returns consensus voting and circuit breaker telemetry."""
    response = client.get("/api/v2/telemetry/agentic_guardrails")
    assert response.status_code == 200
    data = response.json()
    assert "consensus_voting" in data
    assert "circuit_breakers" in data
    assert "checkpoint_efficiency" in data
    assert "crawler_registry" in data
    assert data["consensus_voting"]["status"] == "active"
    assert data["checkpoint_efficiency"]["target_budget_kb"] <= 10.0


def test_api_v2_subagents_sse_stream():
    """Verify /api/v2/subagents/stream provides real-time SSE snapshot with 10 subagents and Boss Orchestrator."""
    response = client.get("/api/v2/subagents/stream?once=true")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    content = response.text
    assert "data:" in content
    assert "subagents_snapshot" in content
    assert "boss_apex" in content
    assert "scout_falcon" in content
    assert "evaluator" in content
    assert "factguard" in content
    assert "scribe" in content
    assert "websurfer" in content
    assert "outreach" in content
    assert "sentinel" in content


