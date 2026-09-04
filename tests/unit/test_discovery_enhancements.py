"""Tests for discovery stage enhancements: US location filter, skill scorer, company discoverer."""

import importlib
import pytest

scanner_mod = importlib.import_module("src.pipeline.1_discovery.scanner")
skill_mod = importlib.import_module("src.pipeline.1_discovery.skill_scorer")
discoverer_mod = importlib.import_module("src.pipeline.1_discovery.company_discoverer")
portal_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")

JobScanner = scanner_mod.JobScanner
SkillScorer = skill_mod.SkillScorer
CompanyDiscoverer = discoverer_mod.CompanyDiscoverer

from src.core.models import JobPosting, JobStatus


# ─── US Location Filter ──────────────────────────────────────────────────────

class TestIsUsLocation:
    """Test the is_us_location class method with edge cases."""

    # Valid US locations
    @pytest.mark.parametrize("location", [
        "San Francisco, CA",
        "New York, NY",
        "Seattle, WA",
        "Austin, TX",
        "Chicago, IL",
        "Boston, MA",
        "Denver, CO",
        "Atlanta, GA",
        "US - Remote",
        "Remote - US",
        "Remote (US)",
        "Remote, US",
        "Remote - California",
        "Remote - Texas",
        "Remote - Washington, D.C.",
        "Remote - California; Remote - Oregon; Remote - Washington",
        "Nevada; Remote - California; Remote - Colorado",
        "Remote",
        "United States - Remote",
        "USA",
        "United States",
        "Silicon Valley",
        "Bay Area",
        "Washington, D.C.",
        "Portland, OR",
    ])
    def test_us_locations_accepted(self, location):
        assert JobScanner.is_us_location(location) is True

    # Invalid non-US locations
    @pytest.mark.parametrize("location", [
        "London, UK",
        "London, England",
        "Toronto, Canada",
        "Toronto, ON, CA",
        "Vancouver, BC",
        "Montreal, Canada",
        "Paris, France",
        "Berlin, Germany",
        "Munich, Germany",
        "Bengaluru, India",
        "Mumbai, India",
        "Singapore",
        "Tokyo, Japan",
        "Sydney, Australia",
        "Dublin, Ireland",
        "Tel Aviv, Israel",
        "Sao Paulo, Brazil",
        "Remote - Worldwide",
        "Remote - EMEA",
        "Remote - Europe",
        "Remote - UK",
        "Remote - Canada",
        "Remote - Global",
        "Remote - International",
        "Hybrid - London, UK",
        "Remote - Ireland",
        "Remote, Germany",
        "",
        None,
        "   ",
    ])
    def test_non_us_locations_rejected(self, location):
        assert JobScanner.is_us_location(location) is False

    # Multi-location with mixed US and non-US
    @pytest.mark.parametrize("location", [
        "San Francisco, CA; Toronto, ON, CAN",
        "SF, CA; London, UK",
        "New York, NY; Paris, France",
        "Austin, TX; Remote - India",
    ])
    def test_mixed_multi_location_rejected(self, location):
        assert JobScanner.is_us_location(location) is False

    # Multi-location all US
    @pytest.mark.parametrize("location", [
        "San Francisco, CA; New York, NY",
        "Remote - California; Remote - Texas",
        "Seattle, WA; Remote - Oregon",
    ])
    def test_all_us_multi_location_accepted(self, location):
        assert JobScanner.is_us_location(location) is True


# ─── Skill Scorer ────────────────────────────────────────────────────────────

class TestSkillScorer:
    """Test skill-based scoring against candidate tech stack."""

    def test_high_signal_match(self):
        scorer = SkillScorer(threshold=0)
        job = JobPosting(
            id="t1", company="Acme", title="Senior .NET Engineer",
            url="https://x.com/1", description="Build C# microservices on AWS with Kafka",
        )
        score = scorer.score_job(job)
        # c#(+20) + .net(+20) + aws(+20) + kafka(+20) + microservices(+10) = 90
        assert score >= 80

    def test_no_match(self):
        scorer = SkillScorer(threshold=0)
        job = JobPosting(
            id="t2", company="Acme", title="Baker",
            url="https://x.com/2", description="Bake bread and pastries daily",
        )
        score = scorer.score_job(job)
        assert score == 0

    def test_threshold_filter(self):
        scorer = SkillScorer(threshold=50)
        high_match = JobPosting(
            id="t3", company="Acme", title="Senior .NET Engineer",
            url="https://x.com/3", description="C# AWS Angular Kafka microservices",
        )
        low_match = JobPosting(
            id="t4", company="Acme", title="Developer",
            url="https://x.com/4", description="Python scripting and REST APIs",
        )
        assert scorer.passes_threshold(high_match) is True
        assert scorer.passes_threshold(low_match) is False

    def test_score_capped_at_100(self):
        scorer = SkillScorer(threshold=0)
        job = JobPosting(
            id="t5", company="Acme", title="Full Stack",
            url="https://x.com/5",
            description="C# .NET AWS Angular Kafka Python TypeScript Docker Kubernetes Lambda DynamoDB",
        )
        assert scorer.score_job(job) <= 100.0

    def test_empty_description(self):
        scorer = SkillScorer(threshold=0)
        job = JobPosting(id="t6", company="Acme", title="Engineer", url="https://x.com/6")
        assert scorer.score_job(job) == 0

    def test_env_threshold_override(self, monkeypatch):
        monkeypatch.setenv("SKILL_MATCH_THRESHOLD", "10")
        scorer = SkillScorer()
        assert scorer.threshold == 10.0


# ─── Board Token Extraction ─────────────────────────────────────────────────

class TestExtractBoardToken:
    """Test extract_board_token function."""

    def test_greenhouse_public_url(self):
        token = portal_mod.extract_board_token("https://boards.greenhouse.io/databricks/jobs/12345")
        assert token == "databricks"

    def test_greenhouse_api_url(self):
        token = portal_mod.extract_board_token("https://boards-api.greenhouse.io/v1/boards/palantir/jobs")
        assert token == "palantir"

    def test_lever_url(self):
        token = portal_mod.extract_board_token("https://jobs.lever.co/stripe/abc-123")
        assert token == "stripe"

    def test_ashby_url(self):
        token = portal_mod.extract_board_token("https://jobs.ashbyhq.com/acme/job-id")
        assert token == "acme"

    def test_smartrecruiters_url(self):
        token = portal_mod.extract_board_token("https://jobs.smartrecruiters.com/sAPi/123")
        assert token == "sapi"

    def test_workday_url(self):
        token = portal_mod.extract_board_token("https://capitalone.wd5.myworkdayjobs.com/en-US/capitalone_careers/job/path")
        assert token is not None

    def test_unknown_url_returns_none(self):
        assert portal_mod.extract_board_token("https://example.com/careers") is None

    def test_empty_url_returns_none(self):
        assert portal_mod.extract_board_token("") is None
        assert portal_mod.extract_board_token(None) is None


# ─── Company Discoverer ─────────────────────────────────────────────────────

class TestCompanyDiscoverer:
    """Test CompanyDiscoverer domain extraction and dedup."""

    def test_extract_domain(self):
        assert CompanyDiscoverer._extract_domain("https://boards.greenhouse.io/acme/jobs/123") == "boards.greenhouse.io"
        assert CompanyDiscoverer._extract_domain("https://jobs.lever.co/stripe/abc") == "jobs.lever.co"
        assert CompanyDiscoverer._extract_domain("") is None

    def test_company_name_from_greenhouse_url(self):
        name = CompanyDiscoverer._company_name_from_url("https://boards.greenhouse.io/acme-corp/jobs/123")
        assert name == "Acme Corp"

    def test_company_name_from_lever_url(self):
        name = CompanyDiscoverer._company_name_from_url("https://jobs.lever.co/stripe/abc")
        assert name == "Stripe"

    def test_company_name_from_ashby_url(self):
        name = CompanyDiscoverer._company_name_from_url("https://jobs.ashbyhq.com/my-company/xyz")
        assert name == "My Company"

    def test_skips_known_ats_domains(self, tmp_path):
        yaml_file = tmp_path / "companies.yaml"
        yaml_file.write_text("companies:\n  - name: Acme\n    domain: acme.com\n    portal_type: greenhouse\n    board_token: acme\n    enabled: true\n    careers_url: https://boards.greenhouse.io/acme\n")
        discoverer = CompanyDiscoverer(companies_file=str(yaml_file))

        # Jobs from aggregator domains should be skipped
        jobs = [
            JobPosting(id="j1", company="SomeCo", title="Engineer",
                       url="https://echojobs.io/someco/123", portal_type="generic"),
        ]
        result = discoverer.discover_from_aggregators(jobs)
        assert len(result) == 0

    def test_skips_already_known_domain(self, tmp_path):
        yaml_file = tmp_path / "companies.yaml"
        yaml_file.write_text("companies:\n  - name: Acme\n    domain: acme.com\n    portal_type: greenhouse\n    board_token: acme\n    enabled: true\n    careers_url: https://boards.greenhouse.io/acme\n")
        discoverer = CompanyDiscoverer(companies_file=str(yaml_file))

        # Job from known domain
        jobs = [
            JobPosting(id="j1", company="Acme", title="Engineer",
                       url="https://boards.greenhouse.io/acme/jobs/123", portal_type="greenhouse"),
            JobPosting(id="j2", company="Acme", title="Senior Engineer",
                       url="https://boards.greenhouse.io/acme/jobs/456", portal_type="greenhouse"),
        ]
        result = discoverer.discover_from_aggregators(jobs)
        assert len(result) == 0
