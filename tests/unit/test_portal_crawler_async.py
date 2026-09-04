"""Unit tests for modernized asynchronous portal crawlers and registry."""

import importlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.models import JobPosting, JobStatus

crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
GreenhouseCrawler = crawler_mod.GreenhouseCrawler
LeverCrawler = crawler_mod.LeverCrawler
AshbyCrawler = crawler_mod.AshbyCrawler
SmartRecruitersCrawler = crawler_mod.SmartRecruitersCrawler
AmazonCrawler = crawler_mod.AmazonCrawler
MicrosoftCrawler = crawler_mod.MicrosoftCrawler
GoogleCareersCrawler = crawler_mod.GoogleCareersCrawler
WorkdayCrawler = crawler_mod.WorkdayCrawler
EchoJobsFeeder = crawler_mod.EchoJobsFeeder
PortalCrawler = crawler_mod.PortalCrawler
CrawlerRegistry = crawler_mod.CrawlerRegistry
register_crawler = crawler_mod.register_crawler
clean_html_description = crawler_mod.clean_html_description


def test_clean_html_description():
    """Test cleaning and unescaping HTML job descriptions."""
    raw = "<p>Senior <b>.NET</b> Engineer</p><br/><div>Requirements: &amp; qualifications</div>"
    cleaned = clean_html_description(raw)
    assert "Senior" in cleaned
    assert ".NET" in cleaned
    assert "Requirements: & qualifications" in cleaned


def test_crawler_registry_decorator():
    """Test register_crawler decorator and registry resolution."""
    registry = CrawlerRegistry()
    available = registry.list_available_crawlers()
    assert "greenhouse" in available
    assert "lever" in available
    assert "ashby" in available
    assert "workday" in available

    gh = registry.get_crawler("greenhouse")
    assert isinstance(gh, GreenhouseCrawler)


@pytest.mark.asyncio
async def test_greenhouse_crawler_async():
    """Test async crawling of Greenhouse jobs board."""
    crawler = GreenhouseCrawler()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobs": [
            {
                "id": 101,
                "title": "Senior Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/stripe/jobs/101",
                "location": {"name": "San Francisco, CA"},
                "content": "<p>Build high scale payment APIs</p>",
                "updated_at": "2026-08-20T10:00:00Z",
            }
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        jobs = await crawler.async_crawl("stripe", "Stripe")
        assert len(jobs) == 1
        assert jobs[0].id == "gh_stripe_101"
        assert jobs[0].title == "Senior Backend Engineer"
        assert jobs[0].company == "Stripe"


@pytest.mark.asyncio
async def test_lever_crawler_async():
    """Test async crawling of Lever jobs board."""
    crawler = LeverCrawler()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": "abc-123",
            "text": "Staff Software Engineer",
            "hostedUrl": "https://jobs.lever.co/netflix/abc-123",
            "categories": {"location": "Remote, US"},
            "descriptionPlain": "Build streaming cloud services",
            "createdAt": 1724300000000,
        }
    ]
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        jobs = await crawler.async_crawl("netflix", "Netflix")
        assert len(jobs) == 1
        assert jobs[0].id == "lever_netflix_abc-123"
        assert jobs[0].title == "Staff Software Engineer"


@pytest.mark.asyncio
async def test_portal_crawler_dispatcher_async():
    """Test unified portal crawler dispatcher async method."""
    dispatcher = PortalCrawler()
    mock_job = JobPosting(
        id="gh_airbnb_1",
        company="Airbnb",
        title="Software Engineer",
        url="https://boards.greenhouse.io/airbnb/jobs/1",
    )
    with patch.object(GreenhouseCrawler, "async_crawl", new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [mock_job]
        results = await dispatcher.async_crawl("greenhouse", "airbnb", "Airbnb")
        assert len(results) == 1
        assert results[0].id == "gh_airbnb_1"
