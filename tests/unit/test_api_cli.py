"""Unit tests for FastAPI REST API and Unified CLI entrypoints."""

from datetime import datetime
import io
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.core.config import Settings, get_settings
from src.core.db.repository import (
    ApplicationRepository,
    ArtifactRepository,
    EvaluationRepository,
    JobRepository,
)
from src.core.models import (
    ApplicationRecord,
    EvaluationResult,
    JobPosting,
    JobStatus,
    SubmissionReceipt,
    TailoredArtifacts,
)
from src.interface.api.routes import app
from src.interface.cli.main import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with isolated temporary SQLite database."""
    test_db = tmp_path / "test_api.db"
    test_settings = Settings(
        db_path=str(test_db),
        min_fit_score=85,
        artifacts_dir=str(tmp_path / "artifacts"),
    )
    monkeypatch.setattr("src.interface.api.routes.get_settings", lambda: test_settings)
    monkeypatch.setattr("src.interface.api.routes.get_job_repo", lambda: JobRepository(str(test_db)))
    monkeypatch.setattr("src.interface.api.routes.get_eval_repo", lambda: EvaluationRepository(str(test_db)))
    monkeypatch.setattr("src.interface.api.routes.get_art_repo", lambda: ArtifactRepository(str(test_db)))
    monkeypatch.setattr("src.interface.api.routes.get_app_repo", lambda: ApplicationRepository(str(test_db)))
    
    return TestClient(app)


def test_api_health(client):
    """Verify healthcheck endpoint returns status healthy and version 1.0.0."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"


def test_api_root_template_rendering(client):
    """Verify root GET / renders modular Jinja2 template with all partials."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    # Verify core layout and tab partials are present in rendered HTML
    assert "OperonJobHuntAI" in html
    assert "tab-kanban" in html
    assert "tab-quick-apply" in html
    assert "tab-graphrag" in html
    assert "tab-live-agent" in html
    assert "tab-settings" in html
    assert "tab-subagent-office" in html
    assert "modal-container" in html
    assert "/static/js/app.js" in html


def test_api_jobs_crud_and_filter(client, tmp_path, monkeypatch):
    """Test listing jobs with and without status filters."""
    test_db = tmp_path / "test_jobs.db"
    repo = JobRepository(str(test_db))
    monkeypatch.setattr("src.interface.api.routes.get_job_repo", lambda: repo)

    j1 = JobPosting(
        id="job_001",
        company="Amazon",
        title="Software Development Engineer II",
        url="https://amazon.jobs/1",
        status=JobStatus.DISCOVERED,
    )
    j2 = JobPosting(
        id="job_002",
        company="Microsoft",
        title="Senior .NET Engineer",
        url="https://microsoft.jobs/2",
        status=JobStatus.MATCHED,
    )
    repo.insert_job(j1)
    repo.insert_job(j2)

    # List all
    res_all = client.get("/api/jobs")
    assert res_all.status_code == 200
    jobs_all = res_all.json()
    assert len(jobs_all) == 2

    # Filter by status
    res_filt = client.get("/api/jobs?status=matched")
    assert res_filt.status_code == 200
    jobs_filt = res_filt.json()
    assert len(jobs_filt) == 1
    assert jobs_filt[0]["company"] == "Microsoft"

    # Get single job
    res_single = client.get("/api/jobs/job_001")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == "job_001"

    # Single job not found
    res_none = client.get("/api/jobs/job_404")
    assert res_none.status_code == 404


def test_api_jobs_enriched_metadata_serialization(client, tmp_path, monkeypatch):
    """Verify jobs endpoint serializes enriched metadata (fit_score, matched_skills, tech_stack, salary, seniority)."""
    test_db = tmp_path / "test_enriched_jobs.db"
    job_repo = JobRepository(str(test_db))
    eval_repo = EvaluationRepository(str(test_db))
    monkeypatch.setattr("src.interface.api.routes.get_job_repo", lambda: job_repo)
    monkeypatch.setattr("src.interface.api.routes.get_eval_repo", lambda: eval_repo)

    job = JobPosting(
        id="job_coinbase_001",
        company="Coinbase",
        title="Senior Backend Engineer - Crypto Infrastructure",
        url="https://coinbase.com/jobs/001",
        portal_type="greenhouse",
        location="San Francisco, CA (Remote)",
        description="Looking for an experienced engineer with C#, .NET, AWS ECS, Kafka, and PostgreSQL experience.",
        status=JobStatus.MATCHED,
        h1b_sponsored=True,
    )
    job_repo.insert_job(job)

    evaluation = EvaluationResult(
        id="eval_coinbase_001",
        job_id="job_coinbase_001",
        fit_score=88.5,
        score=88.5,
        reason="Strong candidate match with 10+ years C# and distributed systems.",
        block_scores={
            "block_a": {
                "title": "Senior Backend Engineer",
                "tech_stack": ["C#", ".NET", "AWS ECS", "Kafka", "PostgreSQL"],
                "seniority_level": "Senior",
            },
            "block_b": {
                "match_score": 92,
                "matched_skills": ["C#", ".NET", "AWS ECS", "Kafka"],
                "missing_skills": ["Solidity"],
            },
            "block_d": {
                "salary_range": "$175,000 - $215,000 USD",
            },
            "block_g": {
                "is_ghost_job": False,
                "work_auth_blocker": False,
            }
        },
        is_ghost_job=False,
        work_auth_blocker=False,
    )
    eval_repo.insert_evaluation(evaluation)

    res = client.get("/api/jobs")
    assert res.status_code == 200
    jobs = res.json()
    assert len(jobs) == 1
    j = jobs[0]
    assert j["id"] == "job_coinbase_001"
    assert j["fit_score"] == 88.5
    assert "C#" in j["matched_skills"]
    assert "AWS ECS" in j["matched_skills"]
    assert j["salary_range"] == "$175,000 - $215,000 USD"
    assert j["seniority"] == "Senior"
    assert j["h1b_sponsored"] is True
    assert j["is_ghost_job"] is False


def test_api_jobs_ingest_from_url(client, tmp_path, monkeypatch):
    """Test POST /api/jobs/ingest with URL."""
    test_db = tmp_path / "test_ingest.db"
    repo = JobRepository(str(test_db))
    monkeypatch.setattr("src.interface.api.routes.get_job_repo", lambda: repo)

    mock_job = JobPosting(
        id="job_stripe_123",
        company="Stripe",
        title="Staff Backend Engineer",
        url="https://boards.greenhouse.io/stripe/jobs/123",
        portal_type="greenhouse",
        description="Build global financial infrastructure using C#/.NET and AWS.",
        status=JobStatus.DISCOVERED,
    )

    with patch("src.interface.api.routes.AdhocIngestor.from_url", return_value=mock_job):
        payload = {"url": "https://boards.greenhouse.io/stripe/jobs/123"}
        response = client.post("/api/jobs/ingest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "job_stripe_123"
        assert data["company"] == "Stripe"
        assert repo.get_job("job_stripe_123") is not None


def test_api_jobs_ingest_from_text(client, tmp_path, monkeypatch):
    """Test POST /api/jobs/ingest with pasted text."""
    test_db = tmp_path / "test_ingest_text.db"
    repo = JobRepository(str(test_db))
    monkeypatch.setattr("src.interface.api.routes.get_job_repo", lambda: repo)

    payload = {
        "company": "Fidelity",
        "title": "Lead Cloud Engineer",
        "description": "Enterprise cloud migrations with AWS ECS and .NET Core.",
        "url": "https://fidelity.com/jobs/99",
    }
    response = client.post("/api/jobs/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["company"] == "Fidelity"
    assert data["title"] == "Lead Cloud Engineer"
    assert repo.get_job(data["id"]) is not None


def test_api_jobs_evaluate(client, tmp_path, monkeypatch):
    """Test POST /api/jobs/{id}/evaluate."""
    test_db = tmp_path / "test_eval.db"
    job_repo = JobRepository(str(test_db))
    eval_repo = EvaluationRepository(str(test_db))
    monkeypatch.setattr("src.interface.api.routes.get_job_repo", lambda: job_repo)
    monkeypatch.setattr("src.interface.api.routes.get_eval_repo", lambda: eval_repo)

    job = JobPosting(
        id="job_eval_1",
        company="Capital One",
        title="Senior .NET Engineer",
        url="https://capitalone.com/1",
        description="C#, AWS, DynamoDB, Microservices.",
        status=JobStatus.DISCOVERED,
    )
    job_repo.insert_job(job)

    mock_eval = EvaluationResult(
        id="eval_1",
        job_id="job_eval_1",
        fit_score=92.0,
        score=92.0,
        reason="Strong .NET and AWS alignment.",
        block_scores={"block_a": {"domain": "Fintech"}},
    )

    with patch("src.interface.api.routes.RubricEvaluator.evaluate", return_value=mock_eval):
        response = client.post("/api/jobs/job_eval_1/evaluate")
        assert response.status_code == 200
        data = response.json()
        assert data["fit_score"] == 92.0
        assert data["job_id"] == "job_eval_1"

        # Check job status transition to MATCHED
        updated_job = job_repo.get_job("job_eval_1")
        assert updated_job.status == JobStatus.MATCHED

    # Test 404 for unknown job
    res_404 = client.post("/api/jobs/unknown_id/evaluate")
    assert res_404.status_code == 404


def test_api_jobs_tailor(client, tmp_path, monkeypatch):
    """Test POST /api/jobs/{id}/tailor."""
    test_db = tmp_path / "test_tailor.db"
    job_repo = JobRepository(str(test_db))
    art_repo = ArtifactRepository(str(test_db))
    monkeypatch.setattr("src.interface.api.routes.get_job_repo", lambda: job_repo)
    monkeypatch.setattr("src.interface.api.routes.get_art_repo", lambda: art_repo)

    job = JobPosting(
        id="job_tailor_1",
        company="Stripe",
        title="Senior Backend Engineer",
        url="https://stripe.com/1",
        status=JobStatus.MATCHED,
    )
    job_repo.insert_job(job)

    mock_artifacts = TailoredArtifacts(
        id="art_1",
        job_id="job_tailor_1",
        resume_pdf_path="/tmp/output/Alex_Rivera_Resume.pdf",
        cover_letter_path="/tmp/output/Cover_Letter.pdf",
        qa_answers={"q1": "10 years experience"},
        linkedin_outreach="Hi recruiter, ...",
    )

    with patch("src.interface.api.routes.ResumeGenerator.generate", return_value=mock_artifacts):
        response = client.post("/api/jobs/job_tailor_1/tailor", json={"target_pages": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job_tailor_1"
        assert data["resume_pdf_path"] == "/tmp/output/Alex_Rivera_Resume.pdf"

        # Check job status transition to TAILORED
        updated_job = job_repo.get_job("job_tailor_1")
        assert updated_job.status == JobStatus.TAILORED

    # Test 404 for unknown job
    res_404 = client.post("/api/jobs/unknown_id/tailor")
    assert res_404.status_code == 404


def test_api_jobs_submit(client, tmp_path, monkeypatch):
    """Test POST /api/jobs/{id}/submit."""
    test_db = tmp_path / "test_submit.db"
    job_repo = JobRepository(str(test_db))
    art_repo = ArtifactRepository(str(test_db))
    app_repo = ApplicationRepository(str(test_db))
    monkeypatch.setattr("src.interface.api.routes.get_job_repo", lambda: job_repo)
    monkeypatch.setattr("src.interface.api.routes.get_art_repo", lambda: art_repo)
    monkeypatch.setattr("src.interface.api.routes.get_app_repo", lambda: app_repo)

    job = JobPosting(
        id="job_sub_1",
        company="Netflix",
        title="Core Engineering Lead",
        url="https://jobs.netflix.com/1",
        status=JobStatus.TAILORED,
    )
    job_repo.insert_job(job)

    mock_receipt = SubmissionReceipt(
        job_id="job_sub_1",
        success=True,
        confirmation_id="NFLX-CONF-999",
        portal_type="greenhouse",
    )

    with patch("src.interface.api.routes.SubmitterEngine.submit", return_value=mock_receipt):
        response = client.post("/api/jobs/job_sub_1/submit", json={"dry_run": True})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["confirmation_id"] == "NFLX-CONF-999"

        # Check job status transition to APPLIED
        updated_job = job_repo.get_job("job_sub_1")
        assert updated_job.status == JobStatus.APPLIED
        assert app_repo.get_by_job_id("job_sub_1") is not None

    # Test 404 for unknown job
    res_404 = client.post("/api/jobs/unknown_id/submit")
    assert res_404.status_code == 404


def test_api_applications_and_analytics(client, tmp_path, monkeypatch):
    """Test GET /api/applications and GET /api/analytics."""
    test_db = tmp_path / "test_app_analytics.db"
    job_repo = JobRepository(str(test_db))
    app_repo = ApplicationRepository(str(test_db))
    monkeypatch.setattr("src.interface.api.routes.get_job_repo", lambda: job_repo)
    monkeypatch.setattr("src.interface.api.routes.get_app_repo", lambda: app_repo)

    # Insert job first for foreign key integrity
    job = JobPosting(
        id="job_001",
        company="Uber",
        title="Staff Engineer",
        url="https://uber.com/1",
        status=JobStatus.APPLIED,
    )
    job_repo.insert_job(job)

    app_rec = ApplicationRecord(
        id="app_001",
        job_id="job_001",
        company="Uber",
        title="Staff Engineer",
        status=JobStatus.APPLIED,
    )
    app_repo.insert_application(app_rec)

    # Applications endpoint
    res_apps = client.get("/api/applications")
    assert res_apps.status_code == 200
    apps_data = res_apps.json()
    assert len(apps_data) == 1
    assert apps_data[0]["company"] == "Uber"

    # Analytics endpoint
    res_analytics = client.get("/api/analytics")
    assert res_analytics.status_code == 200
    metrics = res_analytics.json()
    assert metrics["total_applied"] == 1
    assert metrics["total_active"] == 1


def test_api_settings_get_post(client, tmp_path, monkeypatch):
    """Test GET and POST /api/settings."""
    settings_obj = Settings(min_fit_score=85)
    monkeypatch.setattr("src.interface.api.routes.get_settings", lambda: settings_obj)

    # GET
    res_get = client.get("/api/settings")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["min_fit_score"] == 85

    # POST update
    res_post = client.post("/api/settings", json={"min_fit_score": 90})
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert data_post["min_fit_score"] == 90


def test_api_stories_and_agent_status(client):
    """Test GET /api/stories and GET /api/agent/status."""
    res_stories = client.get("/api/stories")
    assert res_stories.status_code == 200
    stories_data = res_stories.json()
    assert "stories" in stories_data
    assert "metrics" in stories_data
    assert "skills" in stories_data

    res_agent = client.get("/api/agent/status")
    assert res_agent.status_code == 200
    agent_data = res_agent.json()
    assert "status" in agent_data
    assert "logs" in agent_data


# ─────────────────────────────────────────────────────────────────────────────
# CLI Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_cli_status(tmp_path, monkeypatch, capsys):
    """Test `careergraph status` CLI command."""
    test_db = tmp_path / "cli_status.db"
    repo = JobRepository(str(test_db))
    repo.insert_job(
        JobPosting(
            id="job_cli_1",
            company="Apple",
            title="Senior Systems Engineer",
            url="https://apple.com/1",
            status=JobStatus.DISCOVERED,
        )
    )

    with patch("src.interface.cli.main.get_job_repo", return_value=repo), \
         patch("src.interface.cli.main.get_app_repo", return_value=ApplicationRepository(str(test_db))):
        exit_code = main(["status"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "Pipeline Summary" in captured
        assert "Apple" in captured or "discovered" in captured.lower()


def test_cli_scan(capsys):
    """Test `careergraph scan` CLI command."""
    mock_jobs = [
        JobPosting(
            id="j_scan_1",
            company="Google",
            title="Backend SRE",
            url="https://google.com/1",
            status=JobStatus.DISCOVERED,
        )
    ]
    with patch("src.interface.cli.main.JobScanner.scan_all", return_value=mock_jobs):
        exit_code = main(["scan"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "Discovered 1 new job" in captured


def test_cli_ingest(capsys):
    """Test `careergraph ingest <url>` CLI command."""
    mock_job = JobPosting(
        id="j_ingest_1",
        company="Databricks",
        title="Platform Engineer",
        url="https://jobs.lever.co/databricks/1",
        status=JobStatus.DISCOVERED,
    )
    with patch("src.interface.cli.main.AdhocIngestor.from_url", return_value=mock_job), \
         patch("src.interface.cli.main.get_job_repo") as mock_repo_getter:
        mock_repo = MagicMock()
        mock_repo.insert_job.side_effect = lambda j: j
        mock_repo_getter.return_value = mock_repo
        exit_code = main(["ingest", "https://jobs.lever.co/databricks/1"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "Ingested: Databricks - Platform Engineer" in captured


def test_cli_evaluate(capsys):
    """Test `careergraph evaluate <id>` CLI command."""
    mock_job = JobPosting(
        id="j_eval_1",
        company="Microsoft",
        title="Lead .NET Engineer",
        url="https://careers.microsoft.com/1",
        status=JobStatus.DISCOVERED,
    )
    mock_eval = EvaluationResult(
        id="ev_1",
        job_id="j_eval_1",
        fit_score=94.0,
        reason="Direct .NET 8 and AWS match.",
    )
    with patch("src.interface.cli.main.get_job_repo") as mock_repo_getter, \
         patch("src.interface.cli.main.RubricEvaluator.evaluate", return_value=mock_eval), \
         patch("src.interface.cli.main.get_eval_repo"):
        mock_repo = MagicMock()
        mock_repo.get_job.return_value = mock_job
        mock_repo_getter.return_value = mock_repo

        exit_code = main(["evaluate", "j_eval_1"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "Score: 94.0/100" in captured


def test_cli_tailor(capsys):
    """Test `careergraph tailor <id>` CLI command."""
    mock_job = JobPosting(
        id="j_tailor_1",
        company="Amazon",
        title="SDE II",
        url="https://amazon.jobs/1",
        status=JobStatus.MATCHED,
    )
    mock_artifacts = TailoredArtifacts(
        id="art_1",
        job_id="j_tailor_1",
        resume_pdf_path="./output/Alex_Rivera_Resume.pdf",
        cover_letter_path="./output/Cover_Letter.pdf",
    )
    with patch("src.interface.cli.main.get_job_repo") as mock_repo_getter, \
         patch("src.interface.cli.main.ResumeGenerator.generate", return_value=mock_artifacts), \
         patch("src.interface.cli.main.get_art_repo"):
        mock_repo = MagicMock()
        mock_repo.get_job.return_value = mock_job
        mock_repo_getter.return_value = mock_repo

        exit_code = main(["tailor", "j_tailor_1"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "Generated ATS Resume" in captured


def test_cli_submit(capsys):
    """Test `careergraph submit <id> --dry-run` CLI command."""
    mock_job = JobPosting(
        id="j_sub_1",
        company="Stripe",
        title="Staff Engineer",
        url="https://jobs.stripe.com/1",
        status=JobStatus.TAILORED,
    )
    mock_receipt = SubmissionReceipt(
        job_id="j_sub_1",
        success=True,
        confirmation_id="DRY_RUN_CONFIRMED",
        portal_type="lever",
    )
    with patch("src.interface.cli.main.get_job_repo") as mock_repo_getter, \
         patch("src.interface.cli.main.get_art_repo") as mock_art_getter, \
         patch("src.interface.cli.main.get_app_repo"), \
         patch("src.interface.cli.main.SubmitterEngine.submit", return_value=mock_receipt):
        mock_repo = MagicMock()
        mock_repo.get_job.return_value = mock_job
        mock_repo_getter.return_value = mock_repo

        mock_art_repo = MagicMock()
        mock_art_repo.get_by_job_id.return_value = TailoredArtifacts(
            job_id="j_sub_1",
            resume_pdf_path="/path/to/resume.pdf",
        )
        mock_art_getter.return_value = mock_art_repo

        exit_code = main(["submit", "j_sub_1", "--dry-run"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "Submission Success: True" in captured
        assert "DRY_RUN_CONFIRMED" in captured


def test_cli_daemon_single_iteration(capsys):
    """Test `careergraph daemon --iterations 1` CLI command."""
    with patch("src.interface.cli.main.JobScanner.scan_all", return_value=[]):
        exit_code = main(["daemon", "--iterations", "1", "--interval", "1"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "Daemon iteration 1 completed" in captured


def test_cli_ui_command():
    """Test `careergraph ui` CLI command."""
    with patch("src.interface.cli.main.uvicorn.run") as mock_uvicorn:
        exit_code = main(["ui", "--port", "8000", "--no-browser"])
        assert exit_code == 0
        assert mock_uvicorn.called


def test_cli_run_command(tmp_path, capsys):
    """Test `careergraph run <job_id>` CLI command."""
    test_db = tmp_path / "cli_run.db"
    repo = JobRepository(str(test_db))
    repo.insert_job(
        JobPosting(
            id="job_run_1",
            company="Anthropic",
            title="Systems Engineer",
            url="https://anthropic.com/jobs/1",
            status=JobStatus.DISCOVERED,
        )
    )

    with patch("src.interface.cli.main.get_job_repo", return_value=repo), \
         patch("src.interface.cli.main.init_dual_database_pool"), \
         patch("src.interface.cli.main.build_careergraph_pipeline") as mock_build:
        mock_app = MagicMock()
        mock_app.invoke.return_value = {
            "current_stage": "READY_FOR_HITL",
            "fit_score": 95.0,
            "resume_pdf_path": "./data/artifacts/resume.pdf",
        }
        mock_build.return_value = mock_app

        exit_code = main(["run", "job_run_1"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "Anthropic" in captured
        assert "READY_FOR_HITL" in captured

