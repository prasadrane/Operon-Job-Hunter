"""Unit tests for recency-first job prioritization in CareerGraph AI."""

from datetime import datetime, timezone, timedelta
import importlib
from unittest.mock import MagicMock
import pytest

from src.core.db.repository import JobRepository
from src.core.models import JobPosting, JobStatus

_scanner_mod = importlib.import_module("src.pipeline.1_discovery.scanner")
JobScanner = _scanner_mod.JobScanner


def test_job_repository_retrieves_jobs_ordered_by_posted_at_desc(tmp_path):
    """Verify JobRepository.get_all_jobs returns the most recently posted jobs first."""
    db_path = str(tmp_path / "test_recency.db")
    repo = JobRepository(db_path=db_path)

    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=10)
    mid_date = now - timedelta(days=2)
    new_date = now - timedelta(hours=1)

    job_old = JobPosting(
        id="job_old_10d",
        company="Stale Corp",
        title="Software Engineer",
        url="https://stale.com/jobs/1",
        posted_at=old_date,
        discovered_at=now - timedelta(days=1),
    )
    job_mid = JobPosting(
        id="job_mid_2d",
        company="Medium Corp",
        title="Backend Engineer",
        url="https://mid.com/jobs/1",
        posted_at=mid_date,
        discovered_at=now - timedelta(days=1),
    )
    job_new = JobPosting(
        id="job_new_1h",
        company="Fresh Startup",
        title="Platform Engineer",
        url="https://fresh.com/jobs/1",
        posted_at=new_date,
        discovered_at=now,
    )

    # Insert in random order
    repo.insert_job(job_old)
    repo.insert_job(job_new)
    repo.insert_job(job_mid)

    all_jobs = repo.get_all_jobs()
    assert len(all_jobs) == 3
    assert all_jobs[0].id == "job_new_1h"
    assert all_jobs[1].id == "job_mid_2d"
    assert all_jobs[2].id == "job_old_10d"


def test_scanner_get_pending_jobs_prioritizes_recency(tmp_path):
    """Verify JobScanner.get_pending_jobs sorts by posted_at DESC."""
    db_path = str(tmp_path / "test_scanner_recency.db")
    scanner = JobScanner(db_path=db_path)

    now = datetime.now(timezone.utc)
    job_1d = JobPosting(
        id="job_1d",
        company="Acme",
        title="SWE",
        url="https://acme.com/jobs/1",
        posted_at=now - timedelta(days=1),
    )
    job_now = JobPosting(
        id="job_now",
        company="Fast Co",
        title="SWE",
        url="https://fast.com/jobs/1",
        posted_at=now,
    )

    scanner.repository.insert_job(job_1d)
    scanner.repository.insert_job(job_now)

    pending = scanner.get_pending_jobs()
    assert len(pending) >= 2
    assert pending[0].id == "job_now"
    assert pending[1].id == "job_1d"
