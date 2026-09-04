"""Unit tests for expanded feeders: YC, BuiltIn, Wellfound, RSS/Atom, and Enterprise ATS crawlers (iCIMS, Taleo, BambooHR)."""

import importlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.models import JobPosting

agg_mod = importlib.import_module("src.pipeline.1_discovery.aggregators")
YCStartupCrawler = agg_mod.YCStartupCrawler
BuiltInCrawler = agg_mod.BuiltInCrawler
WellfoundCrawler = agg_mod.WellfoundCrawler

rss_mod = importlib.import_module("src.pipeline.1_discovery.rss_crawler")
RSSFeedCrawler = rss_mod.RSSFeedCrawler

portal_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
ICIMSCrawler = portal_mod.ICIMSCrawler
TaleoCrawler = portal_mod.TaleoCrawler
BambooHRCrawler = portal_mod.BambooHRCrawler


@pytest.mark.asyncio
async def test_yc_startup_crawler():
    """Test YC Work at a Startup crawler parsing."""
    crawler = YCStartupCrawler()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobs": [
            {
                "id": "yc_101",
                "title": "Senior Backend Engineer (C# / AWS)",
                "company_name": "Supersonic AI (YC W24)",
                "url": "https://www.workatastartup.com/jobs/101",
                "description": "We are building real-time AI backend services.",
                "location": "San Francisco, CA / Remote",
            }
        ]
    }
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        jobs = await crawler.async_fetch_jobs(limit=10)
        assert len(jobs) == 1
        assert jobs[0].company == "Supersonic AI (YC W24)"
        assert "yc_" in jobs[0].id


@pytest.mark.asyncio
async def test_rss_feed_crawler():
    """Test RSS / Atom feed crawler parsing for Greenhouse/Lever."""
    crawler = RSSFeedCrawler()
    sample_rss_xml = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <title>Stripe Careers</title>
        <item>
          <title>Staff Software Engineer - Infrastructure</title>
          <link>https://boards.greenhouse.io/stripe/jobs/456789</link>
          <description>Join Stripe Infrastructure team building distributed cloud services.</description>
          <pubDate>Mon, 24 Aug 2026 12:00:00 GMT</pubDate>
          <guid>456789</guid>
        </item>
      </channel>
    </rss>"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_rss_xml

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        jobs = await crawler.async_fetch_feed("https://boards.greenhouse.io/stripe/feed/atom", "Stripe")
        assert len(jobs) == 1
        assert jobs[0].title == "Staff Software Engineer - Infrastructure"
        assert jobs[0].company == "Stripe"


def test_enterprise_crawlers_instantiation_and_registry():
    """Test registration and instantiation of iCIMS, Taleo, and BambooHR crawlers."""
    assert "icims" in portal_mod._CRAWLER_REGISTRY
    assert "taleo" in portal_mod._CRAWLER_REGISTRY
    assert "bamboohr" in portal_mod._CRAWLER_REGISTRY

    icims = ICIMSCrawler()
    taleo = TaleoCrawler()
    bamboo = BambooHRCrawler()
    assert icims is not None
    assert taleo is not None
    assert bamboo is not None
