"""Unit tests for proprietary Big Tech crawlers (Amazon, Microsoft, Workday) and Workday account profile."""

import importlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.models import JobPosting, JobStatus, WorkdayAccountProfile

_crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
AmazonCrawler = getattr(_crawler_mod, "AmazonCrawler", None)
MicrosoftCrawler = getattr(_crawler_mod, "MicrosoftCrawler", None)
GoogleCareersCrawler = getattr(_crawler_mod, "GoogleCareersCrawler", None)
WorkdayCrawler = getattr(_crawler_mod, "WorkdayCrawler", None)
PortalCrawler = getattr(_crawler_mod, "PortalCrawler", None)


def test_workday_account_profile_validation():
    """Verify WorkdayAccountProfile model validation and default values."""
    profile = WorkdayAccountProfile(
        email="candidate@example.com",
        first_name="Jane",
        last_name="Doe",
        phone="555-0199",
        address_line1="100 Main St",
        city="San Francisco",
        state="CA",
        postal_code="94105",
        is_authorized_us=True,
        needs_sponsorship_future=True,
        veteran_status="not_veteran",
        disability_status="no_disability",
    )
    assert profile.email == "candidate@example.com"
    assert profile.first_name == "Jane"
    assert profile.state == "CA"
    assert profile.is_authorized_us is True
    assert profile.needs_sponsorship_future is True


def test_amazon_crawler_parsing():
    """Verify AmazonCrawler parses amazon.jobs JSON response into JobPosting models."""
    assert AmazonCrawler is not None, "AmazonCrawler should be implemented in portal_crawler"
    crawler = AmazonCrawler()

    mock_resp_data = {
        "hits": 1,
        "jobs": [
            {
                "id_icims": "2600123",
                "title": "Software Development Engineer II",
                "company_name": "Amazon.com Services LLC",
                "city": "Seattle",
                "state": "WA",
                "country_code": "USA",
                "description": "<p>Join AWS DynamoDB team building distributed NoSQL storage.</p>",
                "job_path": "/en/jobs/2600123/software-development-engineer-ii",
            }
        ]
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_resp_data
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        jobs = crawler.crawl()
        assert len(jobs) == 1
        assert jobs[0].id == "amazon_2600123"
        assert jobs[0].company == "Amazon"
        assert jobs[0].title == "Software Development Engineer II"
        assert "Seattle, WA" in jobs[0].location
        assert "DynamoDB" in jobs[0].description
        assert jobs[0].portal_type == "amazon"


def test_microsoft_crawler_parsing():
    """Verify MicrosoftCrawler parses Microsoft Careers API response."""
    assert MicrosoftCrawler is not None, "MicrosoftCrawler should be implemented in portal_crawler"
    crawler = MicrosoftCrawler()

    mock_resp_data = {
        "data": {
            "totalJobs": 1,
            "jobs": [
                {
                    "jobId": "1728394",
                    "title": "Principal Software Engineer - Azure Core",
                    "properties": {
                        "primaryLocation": "Redmond, Washington, United States",
                        "description": "<div>Lead Azure distributed systems architecture in C# and Go.</div>",
                    }
                }
            ]
        }
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_resp_data
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        jobs = crawler.crawl()
        assert len(jobs) == 1
        assert jobs[0].id == "msft_1728394"
        assert jobs[0].company == "Microsoft"
        assert "Principal Software Engineer" in jobs[0].title
        assert "Redmond, Washington" in jobs[0].location
        assert "Azure distributed systems" in jobs[0].description
        assert jobs[0].portal_type == "microsoft"


def test_workday_crawler_parsing():
    """Verify WorkdayCrawler parses Workday public search endpoints."""
    assert WorkdayCrawler is not None, "WorkdayCrawler should be implemented in portal_crawler"
    crawler = WorkdayCrawler()

    mock_resp_data = {
        "total": 1,
        "jobPostings": [
            {
                "bulletFields": ["R123456"],
                "title": "Lead Software Engineer, Cloud Platform",
                "externalPath": "/job/McLean-VA/Lead-Software-Engineer_R123456",
                "locationsText": "McLean, VA",
            }
        ]
    }

    async def fake_post(url, **kw):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_resp_data
        return resp

    fake_client = MagicMock()
    fake_client.post = fake_post
    fake_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=fake_client):
        jobs = crawler.crawl(tenant="capitalone", company_name="Capital One", board="Capital_One")
        assert len(jobs) == 1
        assert jobs[0].company == "Capital One"
        assert "Lead Software Engineer" in jobs[0].title
        assert "McLean, VA" in jobs[0].location
        assert jobs[0].portal_type == "workday"


def test_portal_crawler_unified_dispatch():
    """Verify PortalCrawler correctly routes to amazon, microsoft, google, and workday."""
    pc = PortalCrawler()
    with patch.object(pc.amazon_crawler, "crawl", return_value=[JobPosting(id="amz_1", company="Amazon", title="SDE", url="http://amz.com", portal_type="amazon", source="amazon_api", status=JobStatus.DISCOVERED)]):
        jobs = pc.crawl(portal_type="amazon", board_token="amazon")
        assert len(jobs) == 1
        assert jobs[0].company == "Amazon"

    with patch.object(pc.microsoft_crawler, "crawl", return_value=[JobPosting(id="ms_1", company="Microsoft", title="SWE", url="http://ms.com", portal_type="microsoft", source="microsoft_api", status=JobStatus.DISCOVERED)]):
        jobs = pc.crawl(portal_type="microsoft", board_token="microsoft")
        assert len(jobs) == 1
        assert jobs[0].company == "Microsoft"

    with patch.object(pc.workday_crawler, "crawl", return_value=[JobPosting(id="wd_1", company="Nvidia", title="SWE", url="http://wd.com", portal_type="workday", source="workday_api", status=JobStatus.DISCOVERED)]):
        jobs = pc.crawl(portal_type="workday", board_token="nvidia", company_name="Nvidia")
        assert len(jobs) == 1
        assert jobs[0].company == "Nvidia"
