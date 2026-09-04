"""Unit tests for high-volume free tech aggregators (RemoteOK, Jobicy, Hacker News)."""

from datetime import datetime, timezone
import importlib
from unittest.mock import MagicMock, patch
import pytest

_agg_mod = importlib.import_module("src.pipeline.1_discovery.aggregators")
RemoteOKCrawler = _agg_mod.RemoteOKCrawler
JobicyCrawler = _agg_mod.JobicyCrawler
HackerNewsJobsCrawler = _agg_mod.HackerNewsJobsCrawler

_horizon_mod = importlib.import_module("src.pipeline.1_discovery.agents.scout_horizon")
ScoutHorizonAgent = _horizon_mod.ScoutHorizonAgent


def test_remoteok_crawler_ingestion():
    """Verify RemoteOKCrawler fetches US tech jobs and parses metadata."""
    crawler = RemoteOKCrawler()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"legal": "disclaimer"},  # first item is disclaimer metadata
        {
            "id": "rok_101",
            "slug": "senior-backend-engineer",
            "company": "Supabase",
            "position": "Senior Backend Engineer",
            "tags": ["golang", "postgres", "backend"],
            "description": "<p>Build real-time database tooling</p>",
            "url": "https://remoteok.com/remote-jobs/rok_101",
            "apply_url": "https://boards.greenhouse.io/supabase/jobs/101",
            "date": "2026-08-22T12:00:00+00:00",
            "location": "United States",
        },
    ]
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_resp):
        jobs = crawler.fetch_jobs(limit=10)

    assert len(jobs) == 1
    assert jobs[0].company == "Supabase"
    assert jobs[0].title == "Senior Backend Engineer"
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.day == 22
    assert jobs[0].portal_type == "greenhouse"


def test_jobicy_crawler_ingestion():
    """Verify JobicyCrawler fetches US engineering jobs."""
    crawler = JobicyCrawler()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobs": [
            {
                "id": 555,
                "url": "https://jobicy.com/jobs/555-cloud-platform-engineer",
                "jobTitle": "Cloud Platform Engineer",
                "companyName": "Docker",
                "jobGeo": "USA",
                "jobDescription": "AWS ECS, Kubernetes, and Terraform infrastructure.",
                "pubDate": "Fri, 21 Aug 2026 15:30:00 +0000",
            }
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_resp):
        jobs = crawler.fetch_jobs(limit=10)

    assert len(jobs) == 1
    assert jobs[0].company == "Docker"
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.day == 21


def test_hacker_news_jobs_crawler():
    """Verify HackerNewsJobsCrawler parses text postings and direct apply links."""
    crawler = HackerNewsJobsCrawler()
    mock_item_resp = MagicMock()
    mock_item_resp.status_code = 200
    mock_item_resp.json.return_value = {
        "id": 99999,
        "by": "whoishiring",
        "time": 1787400000,
        "text": (
            "Anthropic | Senior Platform Engineer | San Francisco, CA | Full-time | ONSITE / REMOTE<br>"
            "We are building reliable AI infrastructure. Apply at https://jobs.ashbyhq.com/anthropic/123"
        ),
    }

    with patch.object(crawler, "_get_latest_who_is_hiring_kids", return_value=[99999]):
        with patch("httpx.Client.get", return_value=mock_item_resp):
            jobs = crawler.fetch_jobs(limit=5)

    assert len(jobs) >= 1
    assert jobs[0].posted_at is not None
    assert "Anthropic" in jobs[0].company or "whoishiring" in jobs[0].source


def test_scout_horizon_agent_broad_sweep():
    """Verify ScoutHorizonAgent aggregates EchoJobs, RemoteOK, Jobicy, and HN."""
    agent = ScoutHorizonAgent()
    mock_job = MagicMock()
    mock_job.url = "https://example.com/job/1"

    with patch.object(agent.echojobs, "fetch_jobs", return_value=[mock_job]):
        with patch.object(agent.remoteok, "fetch_jobs", return_value=[mock_job]):
            with patch.object(agent.jobicy, "fetch_jobs", return_value=[mock_job]):
                with patch.object(agent.hackernews, "fetch_jobs", return_value=[mock_job]):
                    results = agent.run(max_pages=1)

    assert len(results) >= 1
