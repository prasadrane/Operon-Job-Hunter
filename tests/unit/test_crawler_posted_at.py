"""Unit tests verifying posted_at extraction across Greenhouse, Lever, Ashby, Workday, EchoJobs, and JobSpy."""

from datetime import datetime, timezone
import importlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

_crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
GreenhouseCrawler = _crawler_mod.GreenhouseCrawler
LeverCrawler = _crawler_mod.LeverCrawler
AshbyCrawler = _crawler_mod.AshbyCrawler
WorkdayCrawler = _crawler_mod.WorkdayCrawler
EchoJobsFeeder = _crawler_mod.EchoJobsFeeder

_jobspy_mod = importlib.import_module("src.pipeline.1_discovery.jobspy_scraper")
JobSpyScraper = _jobspy_mod.JobSpyScraper


def test_greenhouse_crawler_extracts_posted_at():
    """Verify GreenhouseCrawler extracts updated_at/created_at timestamp."""
    crawler = GreenhouseCrawler()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "jobs": [
            {
                "id": 12345,
                "title": "Senior Backend Engineer",
                "updated_at": "2026-08-20T10:00:00Z",
                "absolute_url": "https://boards.greenhouse.io/stripe/jobs/12345",
                "location": {"name": "San Francisco, CA"},
                "content": "<p>Build payment infrastructure</p>",
            }
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_resp):
        jobs = crawler.crawl("stripe", "Stripe")

    assert len(jobs) == 1
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.year == 2026 and jobs[0].posted_at.day == 20


def test_lever_crawler_extracts_posted_at_epoch_ms():
    """Verify LeverCrawler converts createdAt epoch milliseconds to UTC datetime."""
    crawler = LeverCrawler()
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {
            "id": "lever_uuid_101",
            "text": "Staff Platform Engineer",
            "createdAt": 1787400000000,
            "hostedUrl": "https://jobs.lever.co/figma/lever_uuid_101",
            "categories": {"location": "Remote, US"},
            "descriptionPlain": "Kubernetes and infrastructure",
        }
    ]
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_resp):
        jobs = crawler.crawl("figma", "Figma")

    assert len(jobs) == 1
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.year == 2026


def test_ashby_crawler_extracts_published_at():
    """Verify AshbyCrawler extracts publishedAt/updatedAt timestamp."""
    crawler = AshbyCrawler()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "apiVersion": "1.0",
        "results": [
            {
                "id": "ashby_101",
                "title": "Cloud Architect",
                "publishedAt": "2026-08-22T08:30:00.000Z",
                "jobUrl": "https://jobs.ashbyhq.com/openai/ashby_101",
                "location": "San Francisco, CA",
                "descriptionHtml": "<p>Distributed systems</p>",
            }
        ],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_resp):
        jobs = crawler.crawl("openai", "OpenAI")

    assert len(jobs) == 1
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.day == 22


def test_workday_crawler_extracts_posted_on_relative_date():
    """Verify WorkdayCrawler parses relative 'postedOn' strings."""
    crawler = WorkdayCrawler()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobPostings": [
            {
                "bulletFields": ["JR-101", "Full time", "Posted 2 Days Ago"],
                "title": "Lead Software Engineer",
                "externalPath": "/job/lead-software-engineer-JR-101",
                "locationsText": "McLean, VA",
            }
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    async def fake_post(url, **kw):
        return mock_resp

    fake_client = MagicMock()
    fake_client.post = fake_post
    fake_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=fake_client):
        jobs = crawler.crawl(
            board_token="capitalone",
            company_name="Capital One",
            careers_url="https://capitalone.wd1.myworkdayjobs.com/Capital_One",
        )

    assert len(jobs) == 1
    assert jobs[0].posted_at is not None
    now = datetime.now(timezone.utc)
    assert abs((now - jobs[0].posted_at).total_seconds()) < (3 * 86400)


def test_echojobs_feeder_extracts_created_at():
    """Verify EchoJobsFeeder parses created_at timestamp and returns postings."""
    feeder = EchoJobsFeeder()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": 999,
            "title": "Principal SRE",
            "organization_name": "Datadog",
            "application_url": "https://boards.greenhouse.io/datadog/jobs/999",
            "created_at": "2026-08-21T18:00:00Z",
            "locations": ["New York, NY"],
        }
    ]
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.get", return_value=mock_resp):
        jobs = feeder.fetch_jobs(max_pages=1)

    assert len(jobs) == 1
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.day == 21


def test_jobspy_scraper_extracts_date_posted_and_multi_title():
    """Verify JobSpyScraper maps date_posted to posted_at and supports multi-role queries."""
    scraper = JobSpyScraper()
    mock_records = [
        {
            "job_url": "https://linkedin.com/jobs/view/12345",
            "company": "Amazon",
            "title": "Software Development Engineer II",
            "location": "Seattle, WA",
            "site": "linkedin",
            "date_posted": "2026-08-22",
            "description": "AWS cloud services development.",
        }
    ]

    with patch.object(scraper, "_scrape_dataframe", return_value=mock_records):
        jobs = scraper.search_jobs(search_term="Software Engineer", location="United States", limit=10)

    assert len(jobs) == 1
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.day == 22

    # Verify multi-title sweep method
    with patch.object(scraper, "search_jobs", return_value=jobs) as mock_search:
        all_swept = scraper.sweep_us_software_engineering_roles(limit_per_role=5)
        assert len(all_swept) >= 1
        assert mock_search.call_count >= 3
