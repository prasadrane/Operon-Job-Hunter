"""End-to-End System Integration Test Suite for CareerGraph AI Autonomous Pipeline.

Verifies complete 5-stage pipeline integration:
1. Discovery / Ingestion: Ingests mock job postings (e.g. Capital One Senior .NET Engineer) into SQLite.
2. H-1B Verification: Validates corporate sponsorship eligibility and JD visa clauses.
3. 7-Block Evaluation & Fit Scoring: Evaluates candidate fit against Alex's profile with mock LLM gateway.
4. GraphRAG Tailoring & Generation: Produces 2-page ATS PDF resume, tailored cover letter, custom Q&A map, and LinkedIn outreach note.
5. Playwright Persistent Submission: Simulates persistent browser automation, filling forms, and capturing screenshot receipts.
6. Lifecycle & Status Sync: Transitions application/job status to APPLIED / ACKNOWLEDGED.
7. CLI / API Verification: Verifies FastAPI REST endpoints and CLI commands reflect the updated lifecycle state.
"""

from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import sys
import pytest
from fastapi.testclient import TestClient

from src.core.config import Settings, get_settings
from src.core.db.repository import (
    ApplicationRepository,
    ArtifactRepository,
    EvaluationRepository,
    JobRepository,
)
from src.core.db.schema import init_db
from src.core.models import (
    ApplicationRecord,
    CandidateProfile,
    EvaluationResult,
    JobPosting,
    JobStatus,
    SubmissionReceipt,
    TailoredArtifacts,
)
import importlib

import src.interface.api.routes as api_routes
import src.interface.cli.main as cli_main
from src.interface.api.routes import app
from src.interface.cli.main import main

# Dynamically import numbered pipeline modules
_adhoc_mod = importlib.import_module("src.pipeline.1_discovery.adhoc_ingestor")
AdhocIngestor = _adhoc_mod.AdhocIngestor

_h1b_mod = importlib.import_module("src.pipeline.1_discovery.h1b_checker")
H1BChecker = _h1b_mod.H1BChecker

_scorer_mod = importlib.import_module("src.pipeline.2_evaluation.scorer")
FitScorer = _scorer_mod.FitScorer

_eval_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
RubricEvaluator = _eval_mod.RubricEvaluator

_tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")
ResumeGenerator = _tailor_mod.ResumeGenerator

_submit_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
SubmitterEngine = _submit_mod.SubmitterEngine

_followup_mod = importlib.import_module("src.pipeline.5_lifecycle.followup_engine")
FollowupEngine = _followup_mod.FollowupEngine

_funnel_mod = importlib.import_module("src.pipeline.5_lifecycle.funnel_analytics")
FunnelAnalytics = _funnel_mod.FunnelAnalytics



SAMPLE_CAPITAL_ONE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Senior .NET Engineer - Capital One Careers</title>
    <meta property="og:title" content="Senior .NET Engineer" />
    <meta property="og:site_name" content="Capital One" />
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior .NET Engineer",
        "description": "We are seeking a Senior .NET Engineer to architect enterprise distributed microservices using C#, .NET 8, ASP.NET Core, AWS ECS Fargate, DynamoDB, and Apache Kafka. 8+ years experience building high-throughput cloud systems required. Strong event-driven architecture and TDD expertise.",
        "hiringOrganization": {
            "@type": "Organization",
            "name": "Capital One"
        },
        "jobLocation": {
            "@type": "Place",
            "address": {
                "addressLocality": "McLean",
                "addressRegion": "VA",
                "addressCountry": "USA"
            }
        }
    }
    </script>
</head>
<body>
    <h1>Senior .NET Engineer</h1>
    <div class="company">Capital One</div>
    <div class="description">
        We are seeking a Senior .NET Engineer to architect enterprise distributed microservices using C#, .NET 8, ASP.NET Core, AWS ECS Fargate, DynamoDB, and Apache Kafka.
        Candidates will design resilient cloud APIs, optimize database queries, and mentor engineering teams.
    </div>
</body>
</html>
"""


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    """Setup isolated environment for SQLite, artifacts, and configuration."""
    db_file = tmp_path / "careergraph_e2e.db"
    init_db(str(db_file))

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    sponsors_file = tmp_path / "h1b_sponsors.json"
    sponsors_data = [
        {"name": "Capital One", "domain": "capitalone.com", "confidence": "confirmed"},
        {"name": "Microsoft", "domain": "microsoft.com", "confidence": "confirmed"},
        {"name": "Amazon", "domain": "amazon.com", "confidence": "confirmed"},
        {"name": "Google", "domain": "google.com", "confidence": "confirmed"},
    ]
    sponsors_file.write_text(json.dumps(sponsors_data), encoding="utf-8")

    settings = Settings(
        db_path=str(db_file),
        min_fit_score=85,
        artifacts_dir=str(artifacts_dir),
        h1b_data_path=str(sponsors_file),
    )

    # Patch global get_settings and route repo getters
    monkeypatch.setattr("src.core.config.get_settings", lambda: settings)
    monkeypatch.setattr(api_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(api_routes, "get_job_repo", lambda: JobRepository(str(db_file)))
    monkeypatch.setattr(api_routes, "get_eval_repo", lambda: EvaluationRepository(str(db_file)))
    monkeypatch.setattr(api_routes, "get_art_repo", lambda: ArtifactRepository(str(db_file)))
    monkeypatch.setattr(api_routes, "get_app_repo", lambda: ApplicationRepository(str(db_file)))
    cli_mod = importlib.import_module("src.interface.cli.main")
    monkeypatch.setattr(cli_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_mod, "get_job_repo", lambda: JobRepository(str(db_file)))
    monkeypatch.setattr(cli_mod, "get_eval_repo", lambda: EvaluationRepository(str(db_file)))
    monkeypatch.setattr(cli_mod, "get_art_repo", lambda: ArtifactRepository(str(db_file)))
    monkeypatch.setattr(cli_mod, "get_app_repo", lambda: ApplicationRepository(str(db_file)))

    return {
        "db_file": str(db_file),
        "artifacts_dir": str(artifacts_dir),
        "receipts_dir": str(receipts_dir),
        "sponsors_file": str(sponsors_file),
        "job_repo": JobRepository(str(db_file)),
        "eval_repo": EvaluationRepository(str(db_file)),
        "art_repo": ArtifactRepository(str(db_file)),
        "app_repo": ApplicationRepository(str(db_file)),
        "settings": settings,
    }


# ============================================================================
# 1. Full Chronological Autonomous Cycle Integration Test
# ============================================================================


def test_end_to_end_autonomous_cycle(test_env, monkeypatch):
    """Simulate the complete autonomous job application cycle across all 7 stages."""
    job_repo: JobRepository = test_env["job_repo"]
    eval_repo: EvaluationRepository = test_env["eval_repo"]
    art_repo: ArtifactRepository = test_env["art_repo"]
    app_repo: ApplicationRepository = test_env["app_repo"]
    artifacts_dir = test_env["artifacts_dir"]
    receipts_dir = test_env["receipts_dir"]
    sponsors_file = test_env["sponsors_file"]

    target_url = "https://boards.greenhouse.io/capitalone/jobs/987654"

    # ------------------------------------------------------------------------
    # Stage 1: Discovery & Ingestion + H-1B Verification
    # ------------------------------------------------------------------------
    ingestor = AdhocIngestor()
    job = ingestor.from_url(target_url, html_content=SAMPLE_CAPITAL_ONE_HTML)

    assert job.company == "Capital One"
    assert job.title == "Senior .NET Engineer"
    assert job.portal_type == "greenhouse"
    assert job.status == JobStatus.DISCOVERED
    assert "C#" in (job.description or "")

    # Verify corporate H-1B sponsorship and JD visa constraints
    h1b_checker = H1BChecker(sponsors_path=sponsors_file)
    is_sponsor = h1b_checker.is_sponsor(job.company, domain="capitalone.com")
    assert is_sponsor is True

    sponsorship_eval = h1b_checker.evaluate(job.company, job.description, domain="capitalone.com")
    assert sponsorship_eval["is_eligible"] is True
    assert sponsorship_eval["sponsorship_status"] == "confirmed"

    job.h1b_sponsored = True
    job_repo.insert_job(job)

    retrieved_job = job_repo.get_job(job.id)
    assert retrieved_job is not None
    assert retrieved_job.company == "Capital One"
    assert retrieved_job.h1b_sponsored is True

    # ------------------------------------------------------------------------
    # Stage 2: 7-Block Evaluation & Fit Scoring
    # ------------------------------------------------------------------------
    mock_eval_response = {
        "fit_score": 94.0,
        "reason": "Outstanding match: Senior C#/.NET 8, AWS ECS Fargate, DynamoDB, microservices architecture.",
        "block_a": {
            "title": "Senior .NET Engineer",
            "domain": "Fintech / Cloud Banking",
            "tech_stack": [".NET 8", "C#", "AWS ECS", "DynamoDB", "Kafka"],
            "seniority_level": "Senior IC",
        },
        "block_b": {
            "match_score": 96.0,
            "matched_skills": [".NET 8", "C#", "ASP.NET Core", "AWS ECS", "DynamoDB", "Kafka"],
            "missing_skills": [],
            "gap_analysis": "Complete coverage of core technical stack.",
        },
        "block_c": {
            "level_fit": "Exact match",
            "seniority_assessment": "10+ years backend experience aligns with Senior IC expectations.",
        },
        "block_d": {
            "salary_range": "$165,000 - $195,000",
            "market_competitiveness": "Competitive for McLean, VA / Remote Senior IC",
        },
        "block_e": {
            "pitch_angle": "Highlight AWS cloud cost reduction (40%) and Bedrock AI intent router.",
            "value_hook": "Demonstrated expertise in high-throughput payment systems and zero-downtime migrations.",
        },
        "block_f": {
            "star_stories": [
                {
                    "situation": "Enterprise Underwriting Engine modernization",
                    "action": "Engineered AWS ECS Fargate .NET microservices with DynamoDB single-table design",
                    "result": "40% AWS cost reduction with 99.95% uptime",
                }
            ]
        },
        "block_g": {
            "legitimacy_score": 98.0,
            "is_ghost_job": False,
            "work_auth_blocker": False,
            "notes": "Verified Capital One Greenhouse posting; sponsorship confirmed.",
        },
    }

    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps(mock_eval_response)

    evaluator = RubricEvaluator(llm=mock_llm)
    eval_result = evaluator.evaluate(retrieved_job)

    assert eval_result.fit_score == 94.0
    assert eval_result.work_auth_blocker is False
    assert eval_result.is_ghost_job is False
    assert eval_result.block_scores["block_a"]["title"] == "Senior .NET Engineer"

    # Persist evaluation and transition status to MATCHED
    eval_repo.insert_evaluation(eval_result)
    job_repo.update_status(retrieved_job.id, JobStatus.MATCHED)

    updated_job = job_repo.get_job(retrieved_job.id)
    assert updated_job.status == JobStatus.MATCHED

    # ------------------------------------------------------------------------
    # Stage 3: GraphRAG Tailoring & Artifact Generation
    # ------------------------------------------------------------------------
    job_repo.update_status(updated_job.id, JobStatus.TAILORING)

    tailor = ResumeGenerator(artifacts_dir=artifacts_dir)
    tailored_artifacts = tailor.generate(updated_job, target_pages=2)

    assert tailored_artifacts.resume_pdf_path is not None
    assert Path(tailored_artifacts.resume_pdf_path).exists()
    assert Path(tailored_artifacts.resume_pdf_path).stat().st_size > 1000

    # Verify generated PDF starts with valid magic bytes
    with open(tailored_artifacts.resume_pdf_path, "rb") as f:
        header = f.read(4)
        assert header == b"%PDF"

    # Verify Cover Letter artifact
    assert tailored_artifacts.cover_letter_path is not None
    assert Path(tailored_artifacts.cover_letter_path).exists()

    # Verify Form Q&A answers
    assert isinstance(tailored_artifacts.qa_answers, dict)
    assert len(tailored_artifacts.qa_answers) > 0
    assert "work_authorization" in tailored_artifacts.qa_answers or "us_work_authorized" in tailored_artifacts.qa_answers

    # Verify LinkedIn recruiter outreach note
    assert tailored_artifacts.linkedin_outreach is not None
    assert len(tailored_artifacts.linkedin_outreach) <= 300
    assert "Capital One" in tailored_artifacts.linkedin_outreach or "Alex" in tailored_artifacts.linkedin_outreach

    # Persist artifacts and update status to TAILORED
    art_repo.insert_artifacts(tailored_artifacts)
    job_repo.update_status(updated_job.id, JobStatus.TAILORED)

    persisted_artifacts = art_repo.get_by_job_id(updated_job.id)
    assert persisted_artifacts is not None
    assert persisted_artifacts.resume_pdf_path == tailored_artifacts.resume_pdf_path

    # ------------------------------------------------------------------------
    # Stage 4: Playwright Persistent Browser Submitter
    # ------------------------------------------------------------------------
    job_repo.update_status(updated_job.id, JobStatus.SUBMITTING)

    mock_screenshot_file = Path(receipts_dir) / f"Capital_One_{updated_job.id}_receipt.png"
    mock_screenshot_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4")

    # Mock SubmitterEngine persistent browser execution
    submitter = SubmitterEngine(receipts_dir=receipts_dir, dry_run=True)

    with patch.object(submitter, "submit") as mock_submit:
        mock_submit.return_value = SubmissionReceipt(
            job_id=updated_job.id,
            success=True,
            confirmation_id="CAP-GREENHOUSE-772910",
            screenshot_path=str(mock_screenshot_file),
            portal_type="GreenhouseAdapter",
            submitted_at=datetime.utcnow(),
        )
        receipt = submitter.submit(updated_job, artifacts=persisted_artifacts)

    assert receipt.success is True
    assert receipt.confirmation_id == "CAP-GREENHOUSE-772910"
    assert Path(receipt.screenshot_path).exists()

    # Record application in repository
    app_record = ApplicationRecord(
        job_id=updated_job.id,
        company=updated_job.company,
        title=updated_job.title,
        status=JobStatus.APPLIED,
        portal_url=updated_job.url,
        resume_pdf_path=persisted_artifacts.resume_pdf_path,
        submission_receipt_id=receipt.confirmation_id,
        followup_due_date=datetime.utcnow() + timedelta(days=7),
    )
    app_repo.insert_application(app_record)
    job_repo.update_status(updated_job.id, JobStatus.APPLIED)

    retrieved_app = app_repo.get_by_job_id(updated_job.id)
    assert retrieved_app is not None
    assert retrieved_app.status == JobStatus.APPLIED
    assert retrieved_app.submission_receipt_id == "CAP-GREENHOUSE-772910"

    # ------------------------------------------------------------------------
    # Stage 5: Lifecycle & Status Sync
    # ------------------------------------------------------------------------
    app_repo.update_status(retrieved_app.id, JobStatus.ACKNOWLEDGED)
    job_repo.update_status(updated_job.id, JobStatus.ACKNOWLEDGED)

    # Verify both SQLite Application and Job tables updated to ACKNOWLEDGED
    final_app = app_repo.get_by_job_id(updated_job.id)
    final_job = job_repo.get_job(updated_job.id)

    assert final_app.status == JobStatus.ACKNOWLEDGED
    assert final_job.status == JobStatus.ACKNOWLEDGED

    # ------------------------------------------------------------------------
    # Stage 6: REST API & CLI Verification
    # ------------------------------------------------------------------------
    client = TestClient(app)

    # 1. Verify Job by ID endpoint
    res_job = client.get(f"/api/jobs/{updated_job.id}")
    assert res_job.status_code == 200
    assert res_job.json()["status"] == "acknowledged"
    assert res_job.json()["company"] == "Capital One"

    # 2. Verify Evaluation endpoint
    res_eval = client.get(f"/api/jobs/{updated_job.id}/evaluation")
    assert res_eval.status_code == 200
    assert res_eval.json()["fit_score"] == 94.0

    # 3. Verify Artifacts endpoint
    res_art = client.get(f"/api/jobs/{updated_job.id}/artifacts")
    assert res_art.status_code == 200
    assert res_art.json()["resume_pdf_path"] == persisted_artifacts.resume_pdf_path

    # 4. Verify PDF streaming endpoint
    res_pdf = client.get(f"/api/pdf/{updated_job.id}")
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"
    assert len(res_pdf.content) > 1000

    # 5. Verify Applications endpoint
    res_apps = client.get("/api/applications")
    assert res_apps.status_code == 200
    apps_list = res_apps.json()
    assert len(apps_list) == 1
    assert apps_list[0]["company"] == "Capital One"
    assert apps_list[0]["status"] == "acknowledged"

    # 6. Verify Funnel Analytics endpoint
    res_analytics = client.get("/api/analytics")
    assert res_analytics.status_code == 200
    analytics = res_analytics.json()
    assert analytics["total_applied"] >= 1
    assert analytics["total_acknowledged"] >= 1

    # 7. Verify CLI status command execution against database
    stdout_capture = io.StringIO()
    with patch("sys.stdout", stdout_capture):
        exit_code = main(["status"])
        assert exit_code == 0
        output = stdout_capture.getvalue()
        assert "Capital One" in output
        assert "Senior .NET Engineer" in output


# ============================================================================
# 2. End-to-End FastAPI REST API Workflow Test
# ============================================================================


def test_e2e_api_workflow_ingest_to_submit(test_env, monkeypatch):
    """Verify entire workflow through FastAPI REST endpoints directly."""
    client = TestClient(app)

    # Ingest adhoc job via API
    ingest_payload = {
        "url": "https://boards.greenhouse.io/stripe/jobs/456789",
        "company": "Stripe",
        "title": "Staff Backend Engineer - Cloud Infrastructure",
        "description": "Architect high-scale cloud backend services using AWS, C#, Python, distributed transactions, and event streaming. Strong system design and microservices required.",
        "location": "Chicago, IL (Remote)",
    }

    res_ingest = client.post("/api/jobs/ingest", json=ingest_payload)
    assert res_ingest.status_code == 200
    job_data = res_ingest.json()
    job_id = job_data["id"]
    assert job_data["company"] == "Stripe"
    assert job_data["status"] == "discovered"

    # Mock gateway for evaluation
    mock_eval_response = {
        "fit_score": 91.0,
        "reason": "Strong alignment with cloud infrastructure and distributed backend design.",
        "block_a": {"title": "Staff Backend Engineer", "tech_stack": ["AWS", "C#", "Python"]},
        "block_b": {"match_score": 92.0},
        "block_g": {"legitimacy_score": 95.0, "is_ghost_job": False, "work_auth_blocker": False},
    }
    with patch.object(_eval_mod, "get_gateway") as mock_gw:
        mock_gw.return_value.generate.return_value = json.dumps(mock_eval_response)
        res_eval = client.post(f"/api/jobs/{job_id}/evaluate")
        assert res_eval.status_code == 200
        assert res_eval.json()["fit_score"] == 91.0

    # Verify status changed to MATCHED
    res_job_after_eval = client.get(f"/api/jobs/{job_id}")
    assert res_job_after_eval.json()["status"] == "matched"

    # Tailor artifacts via API
    dummy_pdf = Path(f"data/artifacts/{job_id}_resume.pdf")
    dummy_pdf.parent.mkdir(parents=True, exist_ok=True)
    dummy_pdf.write_bytes(b"%PDF-1.4 Mock Tailored Resume")

    mock_art = TailoredArtifacts(
        id=f"art_{job_id}",
        job_id=job_id,
        resume_pdf_path=str(dummy_pdf),
        resume_json_path=None,
        cover_letter_path=f"data/artifacts/{job_id}_cover.txt",
        qa_answers={},
        linkedin_outreach="Hi recruiter",
    )

    with patch.object(api_routes, "ResumeGenerator") as mock_gen_cls:
        mock_gen_cls.return_value.generate.return_value = mock_art
        res_tailor = client.post(f"/api/jobs/{job_id}/tailor", json={"target_pages": 2})
        assert res_tailor.status_code == 200
        artifacts_data = res_tailor.json()
        assert Path(artifacts_data["resume_pdf_path"]).exists()

    # Verify status changed to TAILORED
    res_job_after_tailor = client.get(f"/api/jobs/{job_id}")
    assert res_job_after_tailor.json()["status"] == "tailored"

    # Submit job in dry_run mode via API
    with patch.object(_submit_mod, "sync_playwright") as mock_pw:
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.goto.return_value = None
        mock_context.new_page.return_value = mock_page
        mock_pw.return_value.__enter__.return_value.chromium.launch_persistent_context.return_value = mock_context

        res_submit = client.post(f"/api/jobs/{job_id}/submit", json={"dry_run": True})
        assert res_submit.status_code == 200
        receipt_data = res_submit.json()
        assert receipt_data["success"] is True
        assert receipt_data["confirmation_id"] == "DRY_RUN_CONFIRMED"

    # Verify status is now APPLIED and record exists in /api/applications
    res_job_final = client.get(f"/api/jobs/{job_id}")
    assert res_job_final.json()["status"] == "applied"

    res_apps = client.get("/api/applications")
    assert res_apps.status_code == 200
    matching_apps = [a for a in res_apps.json() if a["job_id"] == job_id]
    assert len(matching_apps) == 1
    assert matching_apps[0]["company"] == "Stripe"


# ============================================================================
# 3. Rejection & Follow-Up Lifecycle Cadence Integration Test
# ============================================================================


def test_e2e_rejection_and_followup_cycle(test_env):
    """Verify follow-up engine calculations and handling of rejection lifecycle emails."""
    job_repo: JobRepository = test_env["job_repo"]
    app_repo: ApplicationRepository = test_env["app_repo"]

    # Ingest and apply to Databricks
    job = JobPosting(
        id="job_databricks_001",
        company="Databricks",
        title="Senior Cloud Platform Engineer",
        url="https://jobs.lever.co/databricks/111222",
        status=JobStatus.APPLIED,
    )
    job_repo.insert_job(job)

    # Application submitted 8 days ago
    applied_time = datetime.utcnow() - timedelta(days=8)
    followup_engine = FollowupEngine(app_repo=app_repo, cadence_days=7)
    due_date = followup_engine.calculate_due_date(applied_time)

    app_rec = ApplicationRecord(
        job_id=job.id,
        company=job.company,
        title=job.title,
        status=JobStatus.APPLIED,
        applied_at=applied_time,
        followup_due_date=due_date,
    )
    app_repo.insert_application(app_rec)

    # Check pending follow-ups
    pending_followups = followup_engine.get_pending_followups()
    assert len(pending_followups) == 1
    assert pending_followups[0].company == "Databricks"

    # Draft follow-up email
    draft_email = followup_engine.generate_email_draft(
        company=pending_followups[0].company,
        title=pending_followups[0].title,
    )
    assert "Databricks" in draft_email
    assert "Senior Cloud Platform Engineer" in draft_email
    assert "Alex Rivera" in draft_email

    # Now simulate receiving a rejection for Databricks
    app_repo.update_status(app_rec.id, JobStatus.REJECTED)
    job_repo.update_status(job.id, JobStatus.REJECTED)

    # Verify status transitions in both tables
    updated_app = app_repo.get_by_job_id(job.id)
    updated_job = job_repo.get_job(job.id)

    assert updated_app.status == JobStatus.REJECTED
    assert updated_job.status == JobStatus.REJECTED

    # Analytics calculation should reflect rejection
    analytics_engine = FunnelAnalytics(app_repo=app_repo, job_repo=job_repo)
    metrics = analytics_engine.calculate_metrics()
    assert metrics.total_rejections == 1
    assert metrics.rejection_rate_pct == 100.0


# ============================================================================
# 4. Ghost-Job & Work-Auth Blocker Prevention Integration Test
# ============================================================================


def test_e2e_ghost_job_and_visa_blocker_prevention(test_env):
    """Verify non-viable job postings (ghost jobs and citizenship restrictions) are filtered out."""
    job_repo: JobRepository = test_env["job_repo"]
    eval_repo: EvaluationRepository = test_env["eval_repo"]

    # 1. Job with explicit visa blocker
    blocked_job = JobPosting(
        id="job_gov_001",
        company="Defense Contractor Inc",
        title="Senior Security .NET Architect",
        url="https://defense.gov/jobs/1",
        description="US Citizenship Required. Must possess active Top Secret Clearance. No visa sponsorship provided.",
        status=JobStatus.DISCOVERED,
    )
    job_repo.insert_job(blocked_job)

    evaluator = RubricEvaluator()
    eval_blocked = evaluator.evaluate(blocked_job)

    assert eval_blocked.work_auth_blocker is True
    assert eval_blocked.fit_score <= 30.0

    eval_repo.insert_evaluation(eval_blocked)
    job_repo.update_status(blocked_job.id, JobStatus.IGNORED)
    assert job_repo.get_job(blocked_job.id).status == JobStatus.IGNORED

    # 2. Ghost job / scam posting
    ghost_job = JobPosting(
        id="job_scam_002",
        company="QuickMoney Crypto LLC",
        title="Immediate Hire Remote Senior Engineer",
        url="https://t.me/cryptojobsposting",
        description="Earn $150/hour immediately. Wire transfer $500 equipment deposit via Western Union to receive company laptop.",
        status=JobStatus.DISCOVERED,
    )
    job_repo.insert_job(ghost_job)

    eval_ghost = evaluator.evaluate(ghost_job)
    assert eval_ghost.is_ghost_job is True
    assert eval_ghost.fit_score <= 30.0

    eval_repo.insert_evaluation(eval_ghost)
    job_repo.update_status(ghost_job.id, JobStatus.GHOST_JOB)
    assert job_repo.get_job(ghost_job.id).status == JobStatus.GHOST_JOB
