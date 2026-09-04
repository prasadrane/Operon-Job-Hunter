"""Unit tests for Workday CXS Auto-Resolver and JobSpy High-Yield Parallel Scraper."""

import importlib
import pytest
from unittest.mock import MagicMock, patch

crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
WorkdayCrawler = crawler_mod.WorkdayCrawler
PortalCrawler = crawler_mod.PortalCrawler

jobspy_mod = importlib.import_module("src.pipeline.1_discovery.jobspy_scraper")
JobSpyScraper = jobspy_mod.JobSpyScraper


def test_jobspy_scraper_default_sites_and_parallel_sweep():
    """Verify JobSpy defaults to high-yield sites and parallel sweeps without blocking."""
    scraper = JobSpyScraper()
    assert "glassdoor" not in scraper.default_sites
    assert "zip_recruiter" not in scraper.default_sites
    assert "linkedin" in scraper.default_sites

    mock_records = [
        {"title": "Senior .NET Engineer", "company": "Microsoft", "job_url": "https://linkedin.com/jobs/1"},
        {"title": "Backend Engineer", "company": "Amazon", "job_url": "https://linkedin.com/jobs/2"},
    ]

    with patch.object(scraper, "_scrape_dataframe", return_value=mock_records):
        results = scraper.sweep_us_software_engineering_roles(roles=[".NET Engineer", "Backend Engineer"])
        assert len(results) == 2
        assert results[0].company in ("Microsoft", "Amazon")


@pytest.mark.asyncio
async def test_workday_crawler_cxs_auto_resolution():
    """Verify Workday crawler tries candidate slugs and handles valid CXS payload."""
    crawler = WorkdayCrawler()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobPostings": [
            {
                "title": "Principal Engineer",
                "externalPath": "/job/123",
                "bulletFields": ["JR-101"],
                "locationsText": "New York, NY",
            }
        ]
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
        jobs = await crawler.async_crawl(tenant="capitalone", company_name="Capital One")
        assert len(jobs) == 1
        assert jobs[0].company == "Capital One"
        assert jobs[0].title == "Principal Engineer"
        assert jobs[0].portal_type == "workday"
