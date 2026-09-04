import os
import pytest
from datetime import datetime
from pydantic import ValidationError

from src.core.config import Settings, get_settings
from src.core.models import (
    JobStatus,
    JobPosting,
    EvaluationResult,
    TailoredArtifacts,
    ApplicationRecord,
    SubmissionReceipt,
)


def test_settings_defaults():
    settings = get_settings()
    assert settings.min_fit_score == 72.0
    assert settings.db_path.endswith("careergraph.db")
    assert "browser_profile" in settings.browser_profile_dir
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 8000


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("MIN_FIT_SCORE", "90")
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key_123")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_openrouter_key_456")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token_789")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999888777")
    monkeypatch.setenv("DB_PATH", "./custom_data/custom.db")

    custom_settings = Settings()
    assert custom_settings.min_fit_score == 90
    assert custom_settings.gemini_api_key == "test_gemini_key_123"
    assert custom_settings.openrouter_api_key == "test_openrouter_key_456"
    assert custom_settings.telegram_bot_token == "test_bot_token_789"
    assert custom_settings.telegram_chat_id == "999888777"
    assert custom_settings.db_path == "./custom_data/custom.db"


def test_job_status_enum():
    assert JobStatus.DISCOVERED.value == "discovered"
    assert JobStatus.EVALUATING.value == "evaluating"
    assert JobStatus.MATCHED.value == "matched"
    assert JobStatus.TAILORING.value == "tailoring"
    assert JobStatus.TAILORED.value == "tailored"
    assert JobStatus.SUBMITTING.value == "submitting"
    assert JobStatus.APPLIED.value == "applied"
    assert JobStatus.INTERVIEWING.value == "interviewing"
    assert JobStatus.OFFER.value == "offer"
    assert JobStatus.REJECTED.value == "rejected"
    assert JobStatus.GHOST_JOB.value == "ghost_job"
    assert JobStatus.IGNORED.value == "ignored"
    assert JobStatus.FAILED.value == "failed"


def test_job_posting_model():
    job = JobPosting(
        id="job123",
        company="Capital One",
        title="Senior .NET Engineer",
        url="https://capitalone.com/jobs/123",
        portal_type="greenhouse",
        source="scraped_nightly",
        status=JobStatus.DISCOVERED,
        location="McLean, VA (Hybrid)",
        description="Looking for senior C# .NET engineer with AWS experience.",
        h1b_sponsored=True,
    )
    assert job.id == "job123"
    assert job.company == "Capital One"
    assert job.title == "Senior .NET Engineer"
    assert job.portal_type == "greenhouse"
    assert job.status == JobStatus.DISCOVERED
    assert job.h1b_sponsored is True
    assert isinstance(job.discovered_at, datetime)


def test_job_posting_defaults():
    job = JobPosting(
        id="job456",
        company="Stripe",
        title="Software Engineer",
        url="https://jobs.stripe.com/456",
    )
    assert job.portal_type == "generic"
    assert job.source == "scanner"
    assert job.status == JobStatus.DISCOVERED
    assert job.h1b_sponsored is None
    assert job.description is None


def test_evaluation_result_model():
    eval_res = EvaluationResult(
        job_id="job123",
        fit_score=92.5,
        score=92,
        reason="Strong AWS and .NET Core alignment",
        block_scores={"A_tech_stack": 95, "B_seniority": 90},
        work_auth_blocker=False,
        is_ghost_job=False,
    )
    assert eval_res.job_id == "job123"
    assert eval_res.fit_score == 92.5
    assert eval_res.score == 92
    assert eval_res.work_auth_blocker is False
    assert eval_res.is_ghost_job is False
    assert eval_res.block_scores["A_tech_stack"] == 95


def test_tailored_artifacts_model():
    artifacts = TailoredArtifacts(
        job_id="job123",
        resume_pdf_path="./artifacts/resumes/job123_resume.pdf",
        resume_json_path="./artifacts/resumes/job123_resume.json",
        cover_letter_path="./artifacts/letters/job123_cover.txt",
        qa_answers={"sponsorship": "Will require visa transfer", "years_exp": "10"},
        linkedin_outreach="Hi Recruiter, I noticed your opening...",
    )
    assert artifacts.job_id == "job123"
    assert artifacts.resume_pdf_path.endswith(".pdf")
    assert artifacts.qa_answers["years_exp"] == "10"
    assert artifacts.linkedin_outreach.startswith("Hi Recruiter")
    assert isinstance(artifacts.tailored_at, datetime)


def test_submission_receipt_model():
    receipt = SubmissionReceipt(
        job_id="job123",
        success=True,
        confirmation_id="CONF-998811",
        screenshot_path="./data/screenshots/job123_success.png",
        portal_type="greenhouse",
    )
    assert receipt.job_id == "job123"
    assert receipt.success is True
    assert receipt.confirmation_id == "CONF-998811"
    assert isinstance(receipt.submitted_at, datetime)


def test_application_record_model():
    app = ApplicationRecord(
        id="app_001",
        job_id="job123",
        company="Capital One",
        title="Senior .NET Engineer",
        status=JobStatus.APPLIED,
        portal_url="https://capitalone.com/jobs/123",
        resume_pdf_path="./artifacts/resumes/job123_resume.pdf",
        submission_receipt_id="rec_001",
        followup_due_date=datetime(2026, 8, 29, 12, 0, 0),
    )
    assert app.id == "app_001"
    assert app.company == "Capital One"
    assert app.status == JobStatus.APPLIED
    assert isinstance(app.applied_at, datetime)
    assert app.followup_due_date.day == 29


# ── Portfolio showcase: candidate profile indirection ───────────────────────────
from pathlib import Path


def test_profile_dir_defaults_to_sample():
    s = Settings(_env_file=None)
    assert s.profile_dir == "./data/sample"


def test_profile_path_resolves_under_profile_dir():
    s = Settings(_env_file=None, profile_dir="./data/sample")
    assert s.profile_path("MASTER_RESUME.md") == Path("./data/sample") / "MASTER_RESUME.md"


def test_derived_master_resume_paths():
    s = Settings(_env_file=None, profile_dir="/tmp/prof")
    assert s.master_resume_md_path == Path("/tmp/prof") / "MASTER_RESUME.md"
    assert s.master_resume_jsonl_path == Path("/tmp/prof") / "MASTER_RESUME.jsonl"


def test_companies_config_explicit_override_wins():
    s = Settings(_env_file=None, profile_dir="/tmp/prof", companies_config_path="/elsewhere/companies.yaml")
    assert s.companies_yaml_path == Path("/elsewhere/companies.yaml")


def test_companies_config_defaults_into_profile_dir():
    s = Settings(_env_file=None, profile_dir="/tmp/prof", companies_config_path="")
    assert s.companies_yaml_path == Path("/tmp/prof") / "companies.yaml"

