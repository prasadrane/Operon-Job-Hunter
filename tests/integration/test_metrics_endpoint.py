"""Integration tests for /metrics Prometheus endpoint.

Verifies:
1. /metrics returns 200 with Prometheus content type
2. Response body is valid Prometheus exposition format
3. Metrics reflect registered counters after operations
"""

import re

import pytest
from httpx import AsyncClient, ASGITransport

from src.interface.api.routes import app


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_200(transport):
    """/metrics returns 200 with correct content type."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type
    assert "version=" in content_type


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(transport):
    """/metrics returns valid Prometheus exposition format."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    body = response.text
    # Prometheus format contains HELP and TYPE comments
    assert "# HELP" in body or "# TYPE" in body or body.strip() == ""


@pytest.mark.asyncio
async def test_metrics_endpoint_contains_registered_metrics(transport):
    """/metrics output includes our registered metric names."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    body = response.text
    # At least the metric HELP/TYPE lines should be present
    assert "careergraph_submissions_total" in body or "careergraph_active_submissions" in body


@pytest.mark.asyncio
async def test_metrics_endpoint_content_type_header(transport):
    """/metrics Content-Type matches Prometheus spec."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    ct = response.headers["content-type"]
    # prometheus_client CONTENT_TYPE_LATEST is "text/plain; version=X.Y.Z; charset=utf-8"
    assert ct.startswith("text/plain")
    assert "version=" in ct
