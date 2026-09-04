"""Unit tests for PortalRegistry: URL canonicalization, portal detection, and token extraction."""

import importlib

_mod = importlib.import_module("src.pipeline.1_discovery.portal_registry")
canonicalize_url = getattr(_mod, "canonicalize_url")
classify_portal_from_url = getattr(_mod, "classify_portal_from_url")
extract_board_token = getattr(_mod, "extract_board_token")


def test_classify_portal_from_url():
    """Verify portal detection across major ATS providers."""
    assert classify_portal_from_url("https://boards.greenhouse.io/stripe/jobs/1234") == "greenhouse"
    assert classify_portal_from_url("https://jobs.lever.co/netflix/5678") == "lever"
    assert classify_portal_from_url("https://jobs.ashbyhq.com/figma/9012") == "ashby"
    assert classify_portal_from_url("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/1") == "workday"
    assert classify_portal_from_url("https://jobs.smartrecruiters.com/Square/3456") == "smartrecruiters"
    assert classify_portal_from_url("https://amazon.jobs/en/jobs/7890") == "amazon"
    assert classify_portal_from_url("https://unknowncompany.com/careers/job1") == "generic"


def test_extract_board_token():
    """Verify board token extraction from various ATS URL schemas."""
    assert extract_board_token("https://boards.greenhouse.io/andurilindustries/jobs/5159940007") == "andurilindustries"
    assert extract_board_token("https://boards-api.greenhouse.io/v1/boards/coinbase/jobs") == "coinbase"
    assert extract_board_token("https://jobs.lever.co/databricks/1234") == "databricks"
    assert extract_board_token("https://jobs.ashbyhq.com/ramp/5678") == "ramp"
    assert extract_board_token("https://jobs.smartrecruiters.com/Visa/9012") == "visa"
    assert extract_board_token("https://target.myworkdayjobs.com/targetcareers/job/1") == "targetcareers"


def test_canonicalize_url():
    """Verify UTM parameters and tracking queries are stripped."""
    dirty_url = "https://boards.greenhouse.io/stripe/jobs/123?utm_source=linkedin&utm_medium=job_post&gh_jid=123#app"
    clean_url = canonicalize_url(dirty_url)
    assert "utm_source" not in clean_url
    assert "gh_jid" not in clean_url
    assert clean_url.startswith("https://boards.greenhouse.io/stripe/jobs/123")
