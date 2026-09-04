"""Unit tests for SQLite schema and repository layer."""

import os
import sqlite3
from datetime import datetime
import pytest

from src.core.db.schema import init_db
from src.core.db.repository import (
    JobRepository,
    EvaluationRepository,
    ArtifactRepository,
    ApplicationRepository,
)
from src.core.models import (
    JobPosting,
    JobStatus,
    EvaluationResult,
    TailoredArtifacts,
    ApplicationRecord,
)


@pytest.fixture
def db_path(tmp_path):
    """Fixture providing a temporary database path."""
    db_file = tmp_path / "test_careergraph.db"
    return str(db_file)


def test_init_db_creates_tables_and_indices_and_wal(db_path):
    """Test schema initialization creates tables, enables WAL, and creates indices."""
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check WAL mode
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"

    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert {"jobs", "evaluations", "artifacts", "applications"}.issubset(tables)

    # Check indices
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
    indices = {row[0] for row in cursor.fetchall()}
    assert any("status" in idx for idx in indices)
    assert any("url" in idx for idx in indices)

    conn.close()


def test_job_repository_crud_and_status(db_path):
    """Test JobRepository CRUD, retrieval, status update, and deletion."""
    repo = JobRepository(db_path)

    job = JobPosting(
        id="job_001",
        company="Stripe",
        title="Backend Staff Engineer",
        url="https://jobs.stripe.com/1",
        portal_type="lever",
        source="ad_hoc_ui",
        status=JobStatus.DISCOVERED,
        location="Remote, US",
        description="Senior backend engineer with distributed systems experience.",
        h1b_sponsored=True,
    )
    repo.insert_job(job)

    # Retrieval
    retrieved = repo.get_job("job_001")
    assert retrieved is not None
    assert retrieved.id == "job_001"
    assert retrieved.company == "Stripe"
    assert retrieved.title == "Backend Staff Engineer"
    assert retrieved.portal_type == "lever"
    assert retrieved.status == JobStatus.DISCOVERED
    assert retrieved.h1b_sponsored is True

    # Status update
    repo.update_status("job_001", JobStatus.EVALUATING)
    updated = repo.get_job("job_001")
    assert updated is not None
    assert updated.status == JobStatus.EVALUATING

    # Full update
    updated.title = "Principal Backend Engineer"
    repo.update_job(updated)
    refetched = repo.get_job("job_001")
    assert refetched.title == "Principal Backend Engineer"

    # Deletion
    assert repo.delete_job("job_001") is True
    assert repo.get_job("job_001") is None
    assert repo.delete_job("job_001") is False


def test_job_repository_query_by_status(db_path):
    """Test querying jobs by status."""
    repo = JobRepository(db_path)

    job1 = JobPosting(
        id="job_1",
        company="Company A",
        title="Software Engineer",
        url="https://companya.com/job1",
        status=JobStatus.DISCOVERED,
    )
    job2 = JobPosting(
        id="job_2",
        company="Company B",
        title="Data Engineer",
        url="https://companyb.com/job2",
        status=JobStatus.DISCOVERED,
    )
    job3 = JobPosting(
        id="job_3",
        company="Company C",
        title="Cloud Architect",
        url="https://companyc.com/job3",
        status=JobStatus.MATCHED,
    )

    repo.insert_job(job1)
    repo.insert_job(job2)
    repo.insert_job(job3)

    discovered = repo.get_jobs_by_status(JobStatus.DISCOVERED)
    assert len(discovered) == 2
    ids = {j.id for j in discovered}
    assert ids == {"job_1", "job_2"}

    matched = repo.get_jobs_by_status("matched")
    assert len(matched) == 1
    assert matched[0].id == "job_3"

    all_jobs = repo.get_all_jobs()
    assert len(all_jobs) == 3


def test_job_repository_deduplication(db_path):
    """Test deduplication check by URL."""
    repo = JobRepository(db_path)

    test_url = "https://careers.google.com/jobs/results/123"
    assert repo.is_duplicate(test_url) is False
    assert repo.get_job_by_url(test_url) is None

    job = JobPosting(
        id="job_goog",
        company="Google",
        title="Staff Software Engineer",
        url=test_url,
        status=JobStatus.DISCOVERED,
    )
    repo.insert_job(job)

    assert repo.is_duplicate(test_url) is True
    retrieved = repo.get_job_by_url(test_url)
    assert retrieved is not None
    assert retrieved.id == "job_goog"


def test_job_repository_json_serialization(db_path):
    """Test serialization and deserialization of raw_data dict."""
    repo = JobRepository(db_path)

    raw_metadata = {
        "tags": ["python", "fastapi", "docker"],
        "salary_range": {"min": 180000, "max": 230000, "currency": "USD"},
        "nested": {"active": True, "level": 4},
    }

    job = JobPosting(
        id="job_meta",
        company="Netflix",
        title="Senior Platform Engineer",
        url="https://netflix.com/jobs/99",
        raw_data=raw_metadata,
    )
    repo.insert_job(job)

    retrieved = repo.get_job("job_meta")
    assert retrieved is not None
    assert retrieved.raw_data == raw_metadata
    assert retrieved.raw_data["salary_range"]["max"] == 230000


def test_evaluation_repository_crud_and_json(db_path):
    """Test EvaluationRepository insert, get_by_job_id, get_by_id, and JSON block_scores."""
    job_repo = JobRepository(db_path)
    eval_repo = EvaluationRepository(db_path)

    job = JobPosting(
        id="job_eval_1",
        company="Meta",
        title="AI Research Engineer",
        url="https://meta.com/jobs/1",
    )
    job_repo.insert_job(job)

    eval_result = EvaluationResult(
        id="eval_001",
        job_id="job_eval_1",
        fit_score=92.5,
        reason="Strong alignment with GraphRAG and ML deployment experience.",
        block_scores={
            "block_A_skills": 95,
            "block_B_experience": 90,
            "block_C_education": 88,
            "block_D_domain": 94,
            "block_E_compensation": 90,
            "block_F_location": 100,
            "block_G_company_stability": 90,
        },
        work_auth_blocker=False,
        is_ghost_job=False,
    )
    eval_repo.insert_evaluation(eval_result)

    by_job = eval_repo.get_by_job_id("job_eval_1")
    assert by_job is not None
    assert by_job.id == "eval_001"
    assert by_job.fit_score == 92.5
    assert by_job.block_scores["block_A_skills"] == 95
    assert by_job.work_auth_blocker is False
    assert by_job.is_ghost_job is False

    by_id = eval_repo.get_evaluation("eval_001")
    assert by_id is not None
    assert by_id.job_id == "job_eval_1"


def test_artifact_repository_crud_and_json(db_path):
    """Test ArtifactRepository insert, get_by_job_id, and JSON qa_answers."""
    job_repo = JobRepository(db_path)
    art_repo = ArtifactRepository(db_path)

    job = JobPosting(
        id="job_art_1",
        company="Apple",
        title="CoreOS Engineer",
        url="https://apple.com/jobs/2",
    )
    job_repo.insert_job(job)

    qa = {
        "Why Apple?": "Passionate about high-performance systems and consumer privacy.",
        "Years of C++ experience": "8+ years in production systems.",
    }
    artifacts = TailoredArtifacts(
        id="art_001",
        job_id="job_art_1",
        resume_pdf_path="/data/resumes/apple_coreos.pdf",
        resume_json_path="/data/resumes/apple_coreos.json",
        cover_letter_path="/data/resumes/apple_cover.txt",
        qa_answers=qa,
        linkedin_outreach="Hi Hiring Manager, saw your CoreOS opening...",
    )
    art_repo.insert_artifacts(artifacts)

    retrieved = art_repo.get_by_job_id("job_art_1")
    assert retrieved is not None
    assert retrieved.id == "art_001"
    assert retrieved.resume_pdf_path == "/data/resumes/apple_coreos.pdf"
    assert retrieved.qa_answers == qa
    assert retrieved.linkedin_outreach.startswith("Hi Hiring Manager")


def test_application_repository_crud_and_active(db_path):
    """Test ApplicationRepository insert, update stage, and query active applications."""
    job_repo = JobRepository(db_path)
    app_repo = ApplicationRepository(db_path)

    job1 = JobPosting(id="job_app_1", company="Amazon", title="SDE II", url="https://amazon.jobs/1")
    job2 = JobPosting(id="job_app_2", company="Microsoft", title="Senior SWE", url="https://msft.jobs/2")
    job3 = JobPosting(id="job_app_3", company="Uber", title="Backend Engineer", url="https://uber.jobs/3")

    job_repo.insert_job(job1)
    job_repo.insert_job(job2)
    job_repo.insert_job(job3)

    app1 = ApplicationRecord(
        id="app_1",
        job_id="job_app_1",
        company="Amazon",
        title="SDE II",
        status=JobStatus.APPLIED,
        portal_url="https://amazon.jobs/1",
        resume_pdf_path="/data/resumes/amazon.pdf",
    )
    app2 = ApplicationRecord(
        id="app_2",
        job_id="job_app_2",
        company="Microsoft",
        title="Senior SWE",
        status=JobStatus.INTERVIEWING,
        portal_url="https://msft.jobs/2",
    )
    app3 = ApplicationRecord(
        id="app_3",
        job_id="job_app_3",
        company="Uber",
        title="Backend Engineer",
        status=JobStatus.REJECTED,
        portal_url="https://uber.jobs/3",
    )

    app_repo.insert_application(app1)
    app_repo.insert_application(app2)
    app_repo.insert_application(app3)

    # Retrieve by job_id and by id
    retrieved = app_repo.get_by_job_id("job_app_1")
    assert retrieved is not None
    assert retrieved.id == "app_1"
    assert retrieved.status == JobStatus.APPLIED

    # Update stage / status
    app_repo.update_stage("app_1", JobStatus.INTERVIEWING, notes="Screen scheduled for next Tuesday")
    updated = app_repo.get_application("app_1")
    assert updated is not None
    assert updated.status == JobStatus.INTERVIEWING
    assert updated.notes == "Screen scheduled for next Tuesday"

    # Query active applications (should exclude REJECTED, GHOST_JOB, IGNORED, FAILED)
    active_apps = app_repo.get_active_applications()
    assert len(active_apps) == 2
    active_ids = {a.id for a in active_apps}
    assert active_ids == {"app_1", "app_2"}


def test_foreign_key_cascade_deletion(db_path):
    """Test foreign key cascading deletion when a parent job is deleted."""
    job_repo = JobRepository(db_path)
    eval_repo = EvaluationRepository(db_path)
    art_repo = ArtifactRepository(db_path)
    app_repo = ApplicationRepository(db_path)

    job = JobPosting(
        id="job_cascade",
        company="Tesla",
        title="Autopilot Engineer",
        url="https://tesla.com/jobs/auto",
    )
    job_repo.insert_job(job)

    eval_result = EvaluationResult(id="eval_cas", job_id="job_cascade", fit_score=89.0)
    eval_repo.insert_evaluation(eval_result)

    art = TailoredArtifacts(id="art_cas", job_id="job_cascade", resume_pdf_path="/data/tesla.pdf")
    art_repo.insert_artifacts(art)

    app = ApplicationRecord(id="app_cas", job_id="job_cascade", company="Tesla", title="Autopilot Engineer")
    app_repo.insert_application(app)

    # Verify they exist
    assert eval_repo.get_by_job_id("job_cascade") is not None
    assert art_repo.get_by_job_id("job_cascade") is not None
    assert app_repo.get_by_job_id("job_cascade") is not None

    # Delete parent job
    job_repo.delete_job("job_cascade")

    # Verify cascades
    assert job_repo.get_job("job_cascade") is None
    assert eval_repo.get_by_job_id("job_cascade") is None
    assert art_repo.get_by_job_id("job_cascade") is None
    assert app_repo.get_by_job_id("job_cascade") is None


def test_auto_init_and_repository_instances(tmp_path):
    """Test that repositories auto-initialize tables if init_db was not called explicitly."""
    db_file = str(tmp_path / "auto_init.db")
    # Do not call init_db explicitly
    repo = JobRepository(db_file)
    job = JobPosting(
        id="job_auto",
        company="Snowflake",
        title="Database Engineer",
        url="https://snowflake.com/jobs/1",
    )
    repo.insert_job(job)
    assert repo.get_job("job_auto") is not None


def test_job_repository_bulk_upsert_and_delta(db_path):
    """Test bulk upsert and delta high-water mark timestamp query."""
    repo = JobRepository(db_path)
    dt1 = datetime(2026, 8, 20, 10, 0, 0)
    dt2 = datetime(2026, 8, 22, 15, 30, 0)

    jobs = [
        JobPosting(
            id="job_bulk_1",
            company="Datadog",
            title="Senior Backend Engineer",
            url="https://datadog.com/1",
            posted_at=dt1,
            portal_type="greenhouse",
        ),
        JobPosting(
            id="job_bulk_2",
            company="Datadog",
            title="Staff Platform Engineer",
            url="https://datadog.com/2",
            posted_at=dt2,
            portal_type="greenhouse",
        ),
    ]

    count = repo.bulk_upsert_jobs(jobs)
    assert count == 2

    latest_dt = repo.get_latest_job_posted_at(company="Datadog")
    assert latest_dt is not None
    assert latest_dt == dt2

    # Update job 1 via bulk upsert
    jobs[0].title = "Principal Backend Engineer"
    repo.bulk_upsert_jobs([jobs[0]])

    updated = repo.get_job("job_bulk_1")
    assert updated is not None
    assert updated.title == "Principal Backend Engineer"
