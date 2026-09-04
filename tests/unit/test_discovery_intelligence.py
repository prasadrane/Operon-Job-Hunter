"""Unit tests for Discovery Intelligence: WageGate, StreamingDiscoveryQueue, LinkVerifier, and Nexus Parsing."""

import importlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.models import JobPosting, JobStatus

wage_mod = importlib.import_module("src.pipeline.1_discovery.wage_gate")
PrevailingWageGate = wage_mod.PrevailingWageGate

queue_mod = importlib.import_module("src.pipeline.1_discovery.streaming_queue")
StreamingDiscoveryQueue = queue_mod.StreamingDiscoveryQueue

link_mod = importlib.import_module("src.pipeline.1_discovery.link_verifier")
JobLinkVerifier = link_mod.JobLinkVerifier


def test_prevailing_wage_gate_evaluations():
    """Test wage gate filters low-ball or junior compensation below senior thresholds."""
    gate = PrevailingWageGate(min_salary_threshold=130000)

    # High compensation pass
    job_high = JobPosting(
        id="job_high",
        company="Datadog",
        title="Senior Software Engineer",
        url="https://datadog.com/job/1",
        description="Salary range: $165,000 - $210,000 USD plus equity.",
    )
    assert gate.passes_wage_gate(job_high) is True

    # Low-ball underpaid rejection
    job_low = JobPosting(
        id="job_low",
        company="LowPay Co",
        title="Junior C# Developer",
        url="https://lowpay.com/job/2",
        description="Salary: $65,000 - $75,000 per year.",
    )
    assert gate.passes_wage_gate(job_low) is False

    # Unspecified salary should pass through to Stage 2
    job_unspec = JobPosting(
        id="job_unspec",
        company="Google",
        title="Staff Software Engineer",
        url="https://google.com/job/3",
        description="Competitive compensation and benefits package.",
    )
    assert gate.passes_wage_gate(job_unspec) is True


@pytest.mark.asyncio
async def test_streaming_discovery_queue():
    """Test async producer-consumer streaming discovery queue."""
    queue = StreamingDiscoveryQueue()
    received = []

    async def consumer(job: JobPosting):
        received.append(job)

    job1 = JobPosting(id="j1", company="Stripe", title="Staff Engineer", url="https://stripe.com/1")
    job2 = JobPosting(id="j2", company="Block", title="Backend Lead", url="https://block.xyz/2")

    await queue.enqueue(job1)
    await queue.enqueue(job2)
    await queue.process_stream(consumer, max_jobs=2)

    assert len(received) == 2
    assert received[0].id == "j1"
    assert received[1].id == "j2"


@pytest.mark.asyncio
async def test_job_link_verifier():
    """Test async HTTP HEAD dead-link verifier."""
    verifier = JobLinkVerifier()

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200

    mock_resp_404 = MagicMock()
    mock_resp_404.status_code = 404

    with patch("httpx.AsyncClient.head", new_callable=AsyncMock) as mock_head:
        mock_head.side_effect = [mock_resp_200, mock_resp_404]

        is_live_1 = await verifier.verify_link("https://valid.com/jobs/1")
        is_live_2 = await verifier.verify_link("https://invalid.com/jobs/2")

        assert is_live_1 is True
        assert is_live_2 is False
