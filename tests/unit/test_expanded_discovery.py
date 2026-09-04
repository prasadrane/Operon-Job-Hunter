"""Unit tests for expanded high-volume discovery: SmartRecruiters, EchoJobs Feeder, and JobSpy."""

import importlib
import pytest
from unittest.mock import MagicMock, patch

from src.core.models import JobPosting, JobStatus

_crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
SmartRecruitersCrawler = getattr(_crawler_mod, "SmartRecruitersCrawler", None)
EchoJobsFeeder = getattr(_crawler_mod, "EchoJobsFeeder", None)
PortalCrawler = getattr(_crawler_mod, "PortalCrawler", None)

try:
    _jobspy_mod = importlib.import_module("src.pipeline.1_discovery.jobspy_scraper")
    JobSpyScraper = getattr(_jobspy_mod, "JobSpyScraper", None)
except Exception:
    JobSpyScraper = None


def test_smartrecruiters_crawler_parsing():
    """Verify SmartRecruitersCrawler parses public posting API responses."""
    assert SmartRecruitersCrawler is not None, "SmartRecruitersCrawler must be implemented"
    crawler = SmartRecruitersCrawler()

    mock_resp_data = {
        "totalFound": 1,
        "content": [
            {
                "id": "743999912345678",
                "name": "Senior Fullstack Engineer - Payments Platform",
                "company": {"name": "Block"},
                "location": {"city": "San Francisco", "region": "CA", "country": "us"},
                "refNumber": "REF12345T",
                "department": {"label": "Engineering"},
                "releasedDate": "2026-08-20T10:00:00Z",
            }
        ]
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_resp_data
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        jobs = crawler.crawl(board_token="block", company_name="Block")
        assert len(jobs) == 1
        assert jobs[0].id == "sr_block_743999912345678"
        assert jobs[0].company == "Block"
        assert jobs[0].title == "Senior Fullstack Engineer - Payments Platform"
        assert "San Francisco, CA" in jobs[0].location
        assert jobs[0].portal_type == "smartrecruiters"


def test_echojobs_feeder_parsing_and_portal_classification():
    """Verify EchoJobsFeeder parses aggregated postings and classifies original ATS portals."""
    assert EchoJobsFeeder is not None, "EchoJobsFeeder must be implemented"
    feeder = EchoJobsFeeder()

    mock_resp_data = {
        "data": [
            {
                "id": "echo-101",
                "title": "Staff Backend Engineer, Distributed Cache",
                "organization_name": "Datadog",
                "locations": ["New York, NY", "Remote (US)"],
                "url": "https://boards.greenhouse.io/datadog/jobs/5678901",
                "salary_min": 180000,
                "salary_max": 240000,
                "created_at": "2026-08-22T08:00:00Z",
            },
            {
                "id": "echo-102",
                "title": "Lead Software Engineer - Core Infrastructure",
                "organization_name": "Modern Treasury",
                "locations": ["San Francisco, CA"],
                "url": "https://jobs.lever.co/moderntreasury/1234abcd-5678-ef90-1234-567890abcdef",
                "created_at": "2026-08-22T09:00:00Z",
            }
        ]
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_resp_data
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        jobs = feeder.fetch_jobs(max_pages=1)
        assert len(jobs) == 2
        
        # Test Greenhouse classification
        assert jobs[0].company == "Datadog"
        assert jobs[0].portal_type == "greenhouse"
        assert "New York, NY" in jobs[0].location
        
        # Test Lever classification
        assert jobs[1].company == "Modern Treasury"
        assert jobs[1].portal_type == "lever"


def test_jobspy_scraper_fallback_and_search():
    """Verify JobSpyScraper handles mock dataframe rows and graceful fallback."""
    assert JobSpyScraper is not None, "JobSpyScraper must be implemented"
    scraper = JobSpyScraper()

    mock_df_records = [
        {
            "title": "Senior Software Engineer - Python / Go",
            "company": "Scale AI",
            "location": "San Francisco, CA",
            "job_url": "https://www.linkedin.com/jobs/view/1234567890",
            "description": "Build high-throughput LLM evaluation pipelines.",
            "site": "linkedin",
        }
    ]

    with patch.object(scraper, "_scrape_dataframe", return_value=mock_df_records):
        jobs = scraper.search_jobs(search_term="Software Engineer", location="United States", limit=10)
        assert len(jobs) == 1
        assert jobs[0].company == "Scale AI"
        assert jobs[0].title == "Senior Software Engineer - Python / Go"
        assert jobs[0].source == "jobspy_linkedin"
