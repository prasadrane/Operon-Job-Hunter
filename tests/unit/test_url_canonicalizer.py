"""Unit tests for URLCanonicalizer: Parameter stripping, normalization, and fingerprint dedup."""

import importlib
import pytest

canon_mod = importlib.import_module("src.pipeline.1_discovery.url_canonicalizer")
URLCanonicalizer = canon_mod.URLCanonicalizer


def test_strip_tracking_parameters():
    """Verify URL canonicalizer removes UTM, referral, and portal tracking queries."""
    canon = URLCanonicalizer()
    raw_url = "https://boards.greenhouse.io/stripe/jobs/12345?gh_jid=12345&utm_source=linkedin&utm_medium=job_board&ref=xyz"
    clean_url = canon.canonicalize_url(raw_url)
    assert clean_url == "https://boards.greenhouse.io/stripe/jobs/12345"


def test_ashby_lever_canonicalization():
    """Verify normalization across Ashby and Lever URLs."""
    canon = URLCanonicalizer()
    
    # Ashby
    ashby_raw = "https://jobs.ashbyhq.com/Databricks/abc-123?source=google&utm_campaign=hiring"
    assert canon.canonicalize_url(ashby_raw) == "https://jobs.ashbyhq.com/databricks/abc-123"

    # Lever
    lever_raw = "https://jobs.lever.co/Ramp/999-888?lever-origin=applied&lever-source%5B%5D=LinkedIn"
    assert canon.canonicalize_url(lever_raw) == "https://jobs.lever.co/ramp/999-888"


def test_job_fingerprint_generation_and_deduplication():
    """Verify job fingerprint generation deduplicates variations in company suffix and title noise."""
    canon = URLCanonicalizer()

    fp1 = canon.generate_fingerprint(
        company="Stripe, Inc.",
        title="Staff Backend Engineer - Payments",
        location="San Francisco, CA (Remote)",
    )
    fp2 = canon.generate_fingerprint(
        company="Stripe",
        title="Staff Backend Engineer - Payments",
        location="San Francisco, CA",
    )

    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex digest
