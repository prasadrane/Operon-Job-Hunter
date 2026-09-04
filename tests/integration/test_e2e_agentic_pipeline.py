"""End-to-End Agentic Architecture Integration Test Suite for Phase 1.

Verifies the complete orchestrated workflow:
1. Dual DB pool initialization (checkpoints & telemetry in SQLite WAL mode).
2. LangGraph StateGraph execution from DISCOVERED through EVALUATED and READY_FOR_HITL.
3. StateGraph human-in-the-loop (HITL) interrupt mechanism before submit_node.
4. TelegramHITLManager submission lock acquisition and idempotency protection.
5. FastPathSubmitter autofilling and submitting to live MockATSServer (Greenhouse & Lever).
6. Resuming pipeline execution after approval to reach SUBMITTED state with confirmation receipt.
"""

import importlib
import os
import time
from unittest.mock import MagicMock, patch
import pytest
from playwright.sync_api import sync_playwright

from src.core.db.dual_engine import init_dual_database_pool, get_connection
from src.interface.bot.fallback_bundle import FallbackBundleGenerator
from src.interface.bot.telegram_hitl import TelegramHITLManager
from src.pipeline.state_machine import build_careergraph_pipeline
from tests.fixtures.mock_ats_server import MockATSServer

_builder_mod = importlib.import_module("src.pipeline.3_tailoring.career_graph_builder")
CareerGraphBuilder = _builder_mod.CareerGraphBuilder

_tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")
ResumeGenerator = getattr(_tailor_mod, "ResumeGenerator")

_fastpath_mod = importlib.import_module("src.pipeline.4_submission.fastpath_engine")
FastPathSubmitter = _fastpath_mod.FastPathSubmitter


SAMPLE_CANDIDATE_RESUME = """
# Senior Distributed Systems Engineer — Enterprise Corp
### High-Throughput Event Platform
- Architected Kafka streaming pipeline ingesting 15M+ events/day with C# and Python.
- Deployed AWS ECS Fargate microservices achieving 99.99% uptime.
- Optimized Redis caching layer reducing database reads by 40%.
"""


@pytest.fixture(scope="module")
def ats_server():
    """Start and yield Mock ATS HTTP server with ephemeral port."""
    server = MockATSServer()
    server.start()
    time.sleep(0.5)
    yield server
    server.stop()


def test_e2e_agentic_pipeline_greenhouse_flow(ats_server, tmp_path):
    """Verify complete eval -> tailor -> HITL interrupt -> FastPath submit flow on Greenhouse."""
    checkpoints_db = str(tmp_path / "checkpoints_e2e_gh.db")
    telemetry_db = str(tmp_path / "telemetry_e2e_gh.db")
    init_dual_database_pool(checkpoints_path=checkpoints_db, telemetry_path=telemetry_db)

    # 1. Candidate Knowledge Graph
    graph_builder = CareerGraphBuilder()
    graph = graph_builder.build_from_text(SAMPLE_CANDIDATE_RESUME)
    assert "Kafka" in graph.nodes
    assert "C#" in graph.nodes

    # 2. Build LangGraph pipeline
    app = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)

    job_id = "job_gh_integration_001"
    config = {"configurable": {"thread_id": job_id}}

    gh_url = f"{ats_server.get_base_url()}/greenhouse/test_job"
    initial_state = {
        "job_id": job_id,
        "company": "Acme Corp",
        "title": "Staff Software Engineer",
        "url": gh_url,
        "portal_type": "greenhouse",
        "fit_score": 92.0,
        "current_stage": "DISCOVERED",
        "is_ghost_job": False,
        "work_auth_blocker": False,
        "resume_pdf_path": None,
        "cover_letter_path": None,
        "submission_receipt_id": None,
        "qa_answers": {"work_authorization": "Yes", "relocation": "No"},
        "audit_logs": [],
        "errors": [],
        "evaluator_critiques": [],
    }

    # 3. Step 1: Run pipeline up to HITL interrupt
    mock_artifacts = MagicMock()
    mock_artifacts.resume_pdf_path = f"data/artifacts/{job_id}_resume.pdf"
    mock_artifacts.cover_letter_path = f"data/artifacts/{job_id}_cover.txt"
    mock_artifacts.qa_answers = {}

    with patch.object(ResumeGenerator, "generate", return_value=mock_artifacts):
        interrupted_state = app.invoke(initial_state, config=config)

    assert interrupted_state["fit_score"] >= 85.0
    assert interrupted_state["current_stage"] == "READY_FOR_HITL"
    assert interrupted_state["resume_pdf_path"] is not None
    assert interrupted_state["submission_receipt_id"] is None

    # Verify checkpoint stored in SQLite
    checkpoint_info = app.get_state(config)
    assert checkpoint_info.next == ("submit_node",)
    assert checkpoint_info.values["current_stage"] == "READY_FOR_HITL"
    assert checkpoint_info.values["resume_pdf_path"] is not None

    # 4. HITL Approval & Idempotency Lock
    hitl_manager = TelegramHITLManager()
    assert hitl_manager.acquire_submission_lock(job_id) is True
    # Double tap attempt blocked
    assert hitl_manager.acquire_submission_lock(job_id) is False

    # Fallback bundle generation verification
    bundle_gen = FallbackBundleGenerator()
    fallback_bundle = bundle_gen.generate(interrupted_state)
    assert fallback_bundle["job_url"] == gh_url
    assert "Acme Corp" in fallback_bundle["clipboard_text"]

    # 5. Playwright Fast-Path Form Submission against MockATSServer
    dummy_resume = tmp_path / "acme_resume.pdf"
    dummy_resume.write_bytes(b"%PDF-1.4 Mock ATS Resume Content")

    profile = {
        "first_name": "Alex",
        "last_name": "Rivera",
        "email": "alex.rivera@example.com",
        "phone": "555-0199",
        "linkedin_url": "https://linkedin.com/in/alex-rivera",
    }

    submitter = FastPathSubmitter(debounce_ms=100)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(gh_url)

        filled = submitter.fill_profile(page, profile, resume_path=str(dummy_resume))
        assert filled is True

        receipt = submitter.submit(page)
        assert receipt["success"] is True
        assert "GH-CONF-9876" in receipt["confirmation_id"]
        browser.close()

    # 6. Resume LangGraph Pipeline to SUBMITTED state
    resumed_state = app.invoke(None, config=config)
    assert resumed_state["current_stage"] == "SUBMITTED"
    assert f"REC-{job_id}" in resumed_state["submission_receipt_id"]

    # 7. Release lock & verify telemetry connection
    hitl_manager.release_lock(job_id)
    assert hitl_manager.acquire_submission_lock(job_id) is True

    with get_connection("checkpoints") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        assert "checkpoints" in tables or "job_locks" in tables


def test_e2e_agentic_pipeline_lever_flow(ats_server, tmp_path):
    """Verify complete eval -> tailor -> HITL -> FastPath submit flow on Lever."""
    checkpoints_db = str(tmp_path / "checkpoints_e2e_lever.db")
    telemetry_db = str(tmp_path / "telemetry_e2e_lever.db")
    init_dual_database_pool(checkpoints_path=checkpoints_db, telemetry_path=telemetry_db)

    app = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)

    job_id = "job_lever_integration_002"
    config = {"configurable": {"thread_id": job_id}}

    lever_url = f"{ats_server.get_base_url()}/lever/test_job"
    initial_state = {
        "job_id": job_id,
        "company": "BetaScale",
        "title": "Senior Backend Engineer",
        "url": lever_url,
        "portal_type": "lever",
        "fit_score": 91.0,
        "current_stage": "DISCOVERED",
        "is_ghost_job": False,
        "work_auth_blocker": False,
        "resume_pdf_path": None,
        "cover_letter_path": None,
        "submission_receipt_id": None,
        "qa_answers": {},
        "audit_logs": [],
        "errors": [],
        "evaluator_critiques": [],
    }

    # Pipeline up to interrupt
    mock_lever_artifacts = MagicMock()
    mock_lever_artifacts.resume_pdf_path = f"data/artifacts/{job_id}_resume.pdf"
    mock_lever_artifacts.cover_letter_path = f"data/artifacts/{job_id}_cover.txt"
    mock_lever_artifacts.qa_answers = {}

    with patch.object(ResumeGenerator, "generate", return_value=mock_lever_artifacts):
        state_at_hitl = app.invoke(initial_state, config=config)

    assert state_at_hitl["current_stage"] == "READY_FOR_HITL"

    # Playwright Fast-Path on Lever form
    dummy_resume = tmp_path / "betascale_resume.pdf"
    dummy_resume.write_bytes(b"%PDF-1.4 Mock ATS Resume Content")

    profile = {
        "first_name": "Alex",
        "last_name": "Rivera",
        "email": "alex.rivera@example.com",
        "phone": "555-0188",
        "linkedin_url": "https://linkedin.com/in/alex-rivera",
    }

    submitter = FastPathSubmitter(debounce_ms=100)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(lever_url)

        filled = submitter.fill_profile(page, profile, resume_path=str(dummy_resume))
        assert filled is True

        receipt = submitter.submit(page)
        assert receipt["success"] is True
        assert "LEVER-CONF-5432" in receipt["confirmation_id"]
        browser.close()

    # Complete pipeline
    final_state = app.invoke(None, config=config)
    assert final_state["current_stage"] == "SUBMITTED"
