"""Unit tests for Stage 1: Multi-Channel Discovery & H-1B Verification Engine."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

import importlib

from src.core.db.repository import JobRepository
from src.core.db.schema import init_db
from src.core.models import JobPosting, JobStatus

h1b_mod = importlib.import_module("src.pipeline.1_discovery.h1b_checker")
H1BChecker = h1b_mod.H1BChecker

adhoc_mod = importlib.import_module("src.pipeline.1_discovery.adhoc_ingestor")
AdhocIngestor = adhoc_mod.AdhocIngestor

crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
GreenhouseCrawler = crawler_mod.GreenhouseCrawler
LeverCrawler = crawler_mod.LeverCrawler
AshbyCrawler = crawler_mod.AshbyCrawler
PortalCrawler = crawler_mod.PortalCrawler

scanner_mod = importlib.import_module("src.pipeline.1_discovery.scanner")
JobScanner = scanner_mod.JobScanner


# ============================================================================
# 1. H-1B Checker Tests
# ============================================================================


def test_h1b_checker_init_and_lookup(tmp_path):
    """Test H1BChecker loads sponsors and performs matching."""
    sponsors_file = tmp_path / "sponsors.json"
    sponsors_data = [
        {"name": "Microsoft", "domain": "microsoft.com", "confidence": "confirmed"},
        {"name": "Capital One", "domain": "capitalone.com", "confidence": "likely"},
        {"name": "Tata Consultancy Services (TCS)", "domain": "tcs.com", "confidence": "confirmed"},
    ]
    sponsors_file.write_text(json.dumps(sponsors_data))

    checker = H1BChecker(sponsors_path=str(sponsors_file))

    # Exact match
    assert checker.is_sponsor("Microsoft") is True
    assert checker.get_sponsor_confidence("Microsoft") == "confirmed"

    # Normalized name with legal suffixes
    assert checker.is_sponsor("Microsoft Corporation") is True
    assert checker.is_sponsor("Capital One Financial Services Inc.") is True

    # Domain match
    assert checker.is_sponsor("Unknown Alias", domain="microsoft.com") is True
    assert checker.is_sponsor("TCS", domain="tcs.com") is True

    # Unknown company
    assert checker.is_sponsor("Unknown Random LLC", domain="randomunregistered123.com") is False
    assert checker.get_sponsor_confidence("Unknown Random LLC") == "unknown"


def test_h1b_checker_jd_sponsorship_analysis():
    """Test H1BChecker detects visa sponsorship blockers and affirmations in JD text."""
    checker = H1BChecker(sponsors_path=None)

    # Blocker phrases
    jd_blocked_1 = "Applicants must be authorized to work in the US without sponsorship now or in the future."
    jd_blocked_2 = "We are unable to provide visa sponsorship for this role. Must be a US Citizen or Green Card holder."
    jd_blocked_3 = "No visa sponsorship available. Security clearance required."

    assert checker.check_jd_sponsorship(jd_blocked_1) == "no_sponsorship"
    assert checker.check_jd_sponsorship(jd_blocked_2) == "no_sponsorship"
    assert checker.check_jd_sponsorship(jd_blocked_3) == "no_sponsorship"

    # Confirmed sponsorship phrases
    jd_confirmed_1 = "We offer visa sponsorship and H-1B transfer support for qualified candidates."
    jd_confirmed_2 = "Visa sponsorship is available for this senior backend engineering role."
    jd_confirmed_3 = "H-1B sponsorship provided."

    assert checker.check_jd_sponsorship(jd_confirmed_1) == "confirmed"
    assert checker.check_jd_sponsorship(jd_confirmed_2) == "confirmed"
    assert checker.check_jd_sponsorship(jd_confirmed_3) == "confirmed"

    # Neutral / no mention
    jd_neutral = "We are looking for a Senior Software Engineer with 5+ years of Python and AWS experience."
    assert checker.check_jd_sponsorship(jd_neutral) == "unknown"


def test_h1b_checker_evaluate_comprehensive():
    """Test comprehensive evaluate method combining company and JD signals."""
    sponsors = [
        {"name": "Google", "domain": "google.com", "confidence": "confirmed"},
    ]
    checker = H1BChecker(sponsors_data=sponsors)

    # Known sponsor with neutral JD
    res1 = checker.evaluate(company="Google", jd_text="Standard backend role")
    assert res1["is_eligible"] is True
    assert res1["sponsorship_status"] == "confirmed"

    # Known sponsor but JD explicitly blocks sponsorship (role-specific restriction)
    res2 = checker.evaluate(
        company="Google",
        jd_text="Must have active Top Secret clearance. Unable to sponsor visas for this defense project.",
    )
    assert res2["is_eligible"] is False
    assert res2["sponsorship_status"] == "no_sponsorship"

    # Unknown company but JD explicitly offers sponsorship
    res3 = checker.evaluate(
        company="Stealth AI Corp",
        jd_text="We offer full H-1B visa sponsorship and relocation assistance.",
    )
    assert res3["is_eligible"] is True
    assert res3["sponsorship_status"] == "confirmed"


# ============================================================================
# 2. Adhoc Ingestor Tests
# ============================================================================


def test_adhoc_ingestor_detect_portal():
    """Test portal type detection from various job URLs."""
    ingestor = AdhocIngestor()

    assert ingestor.detect_portal("https://boards.greenhouse.io/stripe/jobs/12345") == "greenhouse"
    assert ingestor.detect_portal("https://job-boards.greenhouse.io/openai/jobs/67890") == "greenhouse"
    assert ingestor.detect_portal("https://jobs.lever.co/figma/abc-123") == "lever"
    assert ingestor.detect_portal("https://jobs.ashbyhq.com/notion/def-456") == "ashby"
    assert ingestor.detect_portal("https://capitalone.wd1.myworkdayjobs.com/Capital_One/job/123") == "workday"
    assert ingestor.detect_portal("https://jobs.smartrecruiters.com/Square/789") == "smartrecruiters"
    assert ingestor.detect_portal("https://careers.google.com/jobs/results/999") == "generic"


def test_adhoc_ingestor_html_cleaning():
    """Test stripping noisy tags and cleaning raw HTML."""
    ingestor = AdhocIngestor()

    raw_html = """
    <html>
        <head><title>Job Page</title><script>alert('noise');</script><style>.css{}</style></head>
        <body>
            <nav><a href="/home">Home</a></nav>
            <div class="cookie-banner">Accept all cookies</div>
            <main>
                <h1>Senior Backend Engineer</h1>
                <p>We are looking for a C# / .NET expert with AWS skills.</p>
            </main>
            <footer>Copyright 2026</footer>
        </body>
    </html>
    """
    clean_text = ingestor.extract_clean_text(raw_html)
    assert "Senior Backend Engineer" in clean_text
    assert "C# / .NET expert" in clean_text
    assert "alert('noise')" not in clean_text
    assert "cookie" not in clean_text.lower()
    assert "Copyright 2026" not in clean_text


def test_adhoc_ingestor_json_ld_extraction():
    """Test parsing Schema.org JobPosting from JSON-LD script."""
    ingestor = AdhocIngestor()

    html_with_json_ld = """
    <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org/",
                "@type": "JobPosting",
                "title": "Staff Cloud Architect",
                "hiringOrganization": {
                    "@type": "Organization",
                    "name": "Databricks"
                },
                "jobLocation": {
                    "@type": "Place",
                    "address": {
                        "addressLocality": "San Francisco",
                        "addressRegion": "CA",
                        "addressCountry": "US"
                    }
                },
                "description": "<p>Design high throughput distributed stream systems on AWS.</p>"
            }
            </script>
        </head>
        <body>Some page body</body>
    </html>
    """
    job = ingestor.from_url(
        url="https://databricks.com/careers/12345",
        html_content=html_with_json_ld,
    )

    assert isinstance(job, JobPosting)
    assert job.company == "Databricks"
    assert job.title == "Staff Cloud Architect"
    assert "San Francisco" in (job.location or "")
    assert "high throughput" in (job.description or "")
    assert job.portal_type == "generic"


def test_adhoc_ingestor_html_fallback():
    """Test metadata extraction when JSON-LD is missing."""
    ingestor = AdhocIngestor()

    html_fallback = """
    <html>
        <head>
            <meta property="og:site_name" content="Palantir" />
            <meta property="og:title" content="Lead Platform Engineer" />
        </head>
        <body>
            <h1>Lead Platform Engineer</h1>
            <div class="location">New York, NY (Hybrid)</div>
            <div class="description">Build enterprise graph platforms with .NET Core and Kubernetes.</div>
        </body>
    </html>
    """
    job = ingestor.from_url(
        url="https://jobs.lever.co/palantir/abc-987",
        html_content=html_fallback,
    )

    assert job.company == "Palantir"
    assert job.title == "Lead Platform Engineer"
    assert job.portal_type == "lever"
    assert "enterprise graph platforms" in (job.description or "")


@pytest.mark.asyncio
async def test_adhoc_ingestor_async_fetch():
    """Test asynchronous ingestion with mock HTTP client."""
    ingestor = AdhocIngestor()

    sample_html = """
    <html>
        <head><title>Senior Software Engineer - Stripe</title></head>
        <body>
            <h1>Senior Software Engineer</h1>
            <p>Build scalable payments infrastructure with AWS and Go.</p>
        </body>
    </html>
    """

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = sample_html
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        job = await ingestor.afrom_url("https://boards.greenhouse.io/stripe/jobs/112233")
        assert job.title == "Senior Software Engineer"
        assert job.company == "Stripe"
        assert job.portal_type == "greenhouse"


# ============================================================================
# 3. Portal Crawlers Tests
# ============================================================================


def test_greenhouse_crawler_batch():
    """Test GreenhouseCrawler fetching job board API listings."""
    crawler = GreenhouseCrawler()

    mock_payload = {
        "jobs": [
            {
                "id": 101,
                "title": "Senior Backend Engineer",
                "location": {"name": "Remote, US"},
                "absolute_url": "https://boards.greenhouse.io/figma/jobs/101",
                "content": "<p>Build real-time collaborative engines with C++ and .NET.</p>",
                "updated_at": "2026-08-20T12:00:00Z",
            },
            {
                "id": 102,
                "title": "Principal Architect",
                "location": {"name": "San Francisco, CA"},
                "absolute_url": "https://boards.greenhouse.io/figma/jobs/102",
                "content": "<p>Lead architecture strategy.</p>",
                "updated_at": "2026-08-21T12:00:00Z",
            },
        ]
    }

    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = crawler.crawl(board_token="figma", company_name="Figma")

        assert len(jobs) == 2
        assert jobs[0].company == "Figma"
        assert jobs[0].title == "Senior Backend Engineer"
        assert jobs[0].location == "Remote, US"
        assert jobs[0].portal_type == "greenhouse"
        assert "real-time collaborative engines" in (jobs[0].description or "")


def test_lever_crawler_batch():
    """Test LeverCrawler fetching company postings."""
    crawler = LeverCrawler()

    mock_payload = [
        {
            "id": "lever-uuid-001",
            "text": "Senior .NET Core Engineer",
            "hostedUrl": "https://jobs.lever.co/stripe/lever-uuid-001",
            "categories": {
                "location": "New York, NY",
                "team": "Engineering",
                "commitment": "Full-time",
            },
            "descriptionPlain": "Build robust high-volume financial ledger APIs with C# and AWS.",
            "createdAt": 1771600000000,
        }
    ]

    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = crawler.crawl(board_token="stripe", company_name="Stripe")

        assert len(jobs) == 1
        assert jobs[0].company == "Stripe"
        assert jobs[0].title == "Senior .NET Core Engineer"
        assert jobs[0].location == "New York, NY"
        assert jobs[0].portal_type == "lever"
        assert "high-volume financial ledger" in (jobs[0].description or "")


def test_ashby_crawler_batch():
    """Test AshbyCrawler fetching GraphQL job board postings."""
    crawler = AshbyCrawler()

    mock_graphql_resp = {
        "data": {
            "jobBoard": {
                "jobPostings": [
                    {
                        "id": "ashby-post-1",
                        "title": "Staff Platform Engineer",
                        "locationName": "Remote - US",
                        "isRemote": True,
                        "descriptionHtml": "<p>Design distributed cloud infrastructure with Terraform and AWS.</p>",
                    }
                ]
            }
        }
    }

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_graphql_resp
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = crawler.crawl(board_token="notion", company_name="Notion")

        assert len(jobs) == 1
        assert jobs[0].company == "Notion"
        assert jobs[0].title == "Staff Platform Engineer"
        assert jobs[0].portal_type == "ashby"
        assert jobs[0].location == "Remote - US"


def test_portal_crawler_dispatcher():
    """Test unified PortalCrawler dispatching across portal types."""
    unified = PortalCrawler()

    with patch.object(unified.greenhouse_crawler, "crawl", return_value=[
        JobPosting(id="gh1", company="Figma", title="SWE", url="https://gh.io/1", portal_type="greenhouse")
    ]) as mock_gh:
        results = unified.crawl(portal_type="greenhouse", board_token="figma", company_name="Figma")
        assert len(results) == 1
        mock_gh.assert_called_once_with(board_token="figma", company_name="Figma")


# ============================================================================
# 4. Job Scanner Tests
# ============================================================================


def test_job_scanner_load_companies_yaml(tmp_path):
    """Test JobScanner loading target company watchlist from YAML."""
    yaml_file = tmp_path / "companies.yaml"
    yaml_content = """
    companies:
      - name: Figma
        domain: figma.com
        portal_type: greenhouse
        board_token: figma
        enabled: true
        keywords: ["Backend", "Cloud"]
      - name: Disabled Corp
        domain: disabled.com
        portal_type: lever
        board_token: disabled
        enabled: false
    """
    yaml_file.write_text(yaml_content)

    scanner = JobScanner(companies_file=str(yaml_file))
    companies = scanner.load_companies()

    assert len(companies) == 2
    enabled = [c for c in companies if c.get("enabled", True)]
    assert len(enabled) == 1
    assert enabled[0]["name"] == "Figma"


def test_job_scanner_filter_and_h1b_verification(tmp_path):
    """Test JobScanner filtering jobs by keywords and H-1B verification."""
    sponsors = [{"name": "Figma", "domain": "figma.com", "confidence": "confirmed"}]
    h1b_checker = H1BChecker(sponsors_data=sponsors)
    scanner = JobScanner(h1b_checker=h1b_checker, enable_skill_filter=False)

    # Matching title + sponsor company + neutral JD + US location -> KEEP
    job1 = JobPosting(
        id="j1",
        company="Figma",
        title="Senior Backend Engineer (.NET / Cloud)",
        url="https://gh.io/1",
        location="San Francisco, CA",
        description="Build scalable distributed services on AWS.",
    )
    assert scanner.filter_job(job1, keywords=["Backend", ".NET"], require_h1b=True) is True
    assert job1.h1b_sponsored is True

    # Mismatched title keywords -> DROP
    job2 = JobPosting(
        id="j2",
        company="Figma",
        title="Senior Product Marketing Manager",
        url="https://gh.io/2",
        location="San Francisco, CA",
        description="Drive GTM campaigns.",
    )
    assert scanner.filter_job(job2, keywords=["Backend", "Software"], require_h1b=True) is False

    # Matching title but company is NOT sponsor and JD has no sponsorship -> DROP when require_h1b=True
    job3 = JobPosting(
        id="j3",
        company="NonSponsor LLC",
        title="Senior Backend Engineer",
        url="https://gh.io/3",
        location="New York, NY",
        description="No sponsorship provided.",
    )
    assert scanner.filter_job(job3, keywords=["Backend"], require_h1b=True) is False
    assert job3.h1b_sponsored is False


def test_job_scanner_orchestration_and_db_persistence(tmp_path):
    """Test full scan_all orchestration with SQLite deduplication."""
    db_file = tmp_path / "scanner_test.db"
    init_db(str(db_file))
    job_repo = JobRepository(str(db_file))

    companies_file = tmp_path / "companies.yaml"
    companies_file.write_text("""
    companies:
      - name: Stripe
        domain: stripe.com
        portal_type: lever
        board_token: stripe
        enabled: true
        keywords: ["Backend", "Engineer"]
    """)

    sponsors = [{"name": "Stripe", "domain": "stripe.com", "confidence": "likely"}]
    h1b_checker = H1BChecker(sponsors_data=sponsors)

    mock_crawled_jobs = [
        JobPosting(
            id="stripe-job-1",
            company="Stripe",
            title="Senior Backend Engineer",
            url="https://jobs.lever.co/stripe/stripe-job-1",
            portal_type="lever",
            description="Work on global financial infrastructure.",
            location="Remote, US",
        ),
        JobPosting(
            id="stripe-job-2",
            company="Stripe",
            title="Executive Assistant",
            url="https://jobs.lever.co/stripe/stripe-job-2",
            portal_type="lever",
            description="Administrative support.",
            location="San Francisco, CA",
        ),
    ]

    mock_portal_crawler = MagicMock(spec=PortalCrawler)
    mock_portal_crawler.crawl.return_value = mock_crawled_jobs

    scanner = JobScanner(
        companies_file=str(companies_file),
        h1b_checker=h1b_checker,
        portal_crawler=mock_portal_crawler,
        job_repo=job_repo,
        enable_skill_filter=False,
    )

    discovered = scanner.scan_all(filter_h1b=True, include_aggregators=False)

    # Executive assistant should be filtered out by keywords, backend engineer retained
    assert len(discovered) == 1
    assert discovered[0].id == "stripe-job-1"
    assert discovered[0].h1b_sponsored is True

    # Verify persisted into SQLite
    persisted = job_repo.get_job("stripe-job-1")
    assert persisted is not None
    assert persisted.company == "Stripe"
    assert persisted.status == JobStatus.DISCOVERED

    # Running scan again should deduplicate existing jobs in database
    discovered_second_run = scanner.scan_all(filter_h1b=True, include_aggregators=False)
    assert len(discovered_second_run) == 0


def test_crawler_registry_dynamic_resolution():
    """Verify CrawlerRegistry dynamically resolves crawler tool classes on demand."""
    crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
    CrawlerRegistry = getattr(crawler_mod, "CrawlerRegistry")
    GreenhouseCrawler = getattr(crawler_mod, "GreenhouseCrawler")
    LeverCrawler = getattr(crawler_mod, "LeverCrawler")

    registry = CrawlerRegistry()
    crawler_gh = registry.resolve_crawler("https://boards.greenhouse.io/openai/jobs/1")
    assert isinstance(crawler_gh, GreenhouseCrawler)

    crawler_lever = registry.resolve_crawler("https://jobs.lever.co/spotify/1")
    assert isinstance(crawler_lever, LeverCrawler)

    # Unknown domain falls back to generic / None or default
    crawler_unknown = registry.resolve_crawler("https://unknown-ats.com/job/1")
    assert crawler_unknown is not None


