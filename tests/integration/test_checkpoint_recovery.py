"""Integration tests for LangGraph checkpoint persistence, crash recovery, and WAL mode."""
import sqlite3
import pytest

from src.pipeline.state_machine import build_careergraph_pipeline


def test_checkpoint_recovery_at_submission_stage(tmp_path):
    """Verify state interruption before submission and checkpoint state recovery across restarts."""
    checkpoints_db = str(tmp_path / "checkpoints.db")
    app = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)

    thread_id = "job_stripe_999"
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "job_id": thread_id,
        "company": "Stripe",
        "title": "Staff Engineer",
        "url": "https://boards.greenhouse.io/stripe/jobs/999",
        "portal_type": "greenhouse",
        "fit_score": 94.0,
        "current_stage": "DISCOVERED",
        "is_ghost_job": False,
        "work_auth_blocker": False,
        "resume_pdf_path": None,
        "cover_letter_path": None,
        "submission_receipt_id": None,
        "screenshot_path": None,
        "telegram_message_id": None,
        "qa_answers": {},
        "audit_logs": [],
        "errors": [],
        "evaluator_critiques": [],
    }

    # Step 1: Run graph until human-in-the-loop interruption before submit_node
    import importlib
    from unittest.mock import MagicMock, patch
    _tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")
    ResumeGenerator = getattr(_tailor_mod, "ResumeGenerator")
    mock_artifacts = MagicMock()
    mock_artifacts.resume_pdf_path = f"data/artifacts/{thread_id}_resume.pdf"
    mock_artifacts.cover_letter_path = f"data/artifacts/{thread_id}_cover.txt"
    mock_artifacts.qa_answers = {}

    with patch.object(ResumeGenerator, "generate", return_value=mock_artifacts):
        state_after_tailor = app.invoke(initial_state, config=config)
        assert state_after_tailor["current_stage"] in ["READY_FOR_HITL", "TAILORED"]
        assert state_after_tailor["resume_pdf_path"] is not None
        assert state_after_tailor["submission_receipt_id"] is None

    # Step 2: Simulate process crash/restart by instantiating a fresh pipeline instance pointing to same DB
    resumed_app = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)
    checkpoint_state = resumed_app.get_state(config)
    assert checkpoint_state.values["job_id"] == thread_id
    assert checkpoint_state.values["resume_pdf_path"] is not None
    assert checkpoint_state.next == ("submit_node",)

    # Step 3: Resume execution from the checkpoint through submission
    final_state = resumed_app.invoke(None, config=config)
    assert final_state["current_stage"] == "SUBMITTED"
    assert final_state["submission_receipt_id"] == f"REC-{thread_id}"
    assert len(final_state["audit_logs"]) >= 2


def test_checkpoint_recovery_ghost_job_rejection(tmp_path):
    """Verify conditional edge drops ghost jobs directly to END without reaching submit_node."""
    checkpoints_db = str(tmp_path / "checkpoints.db")
    app = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)

    thread_id = "job_ghost_404"
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "job_id": thread_id,
        "company": "GhostCorp",
        "title": "Senior Engineer",
        "url": "https://ghostcorp.com/jobs/404",
        "portal_type": "greenhouse",
        "fit_score": 0.0,
        "current_stage": "DISCOVERED",
        "is_ghost_job": True,
        "work_auth_blocker": False,
        "resume_pdf_path": None,
        "cover_letter_path": None,
        "submission_receipt_id": None,
        "screenshot_path": None,
        "telegram_message_id": None,
        "qa_answers": {},
        "audit_logs": [],
        "errors": [],
        "evaluator_critiques": [],
    }

    state_after_eval = app.invoke(initial_state, config=config)
    assert state_after_eval["fit_score"] == 40.0
    assert state_after_eval["current_stage"] == "EVALUATED"
    assert state_after_eval.get("resume_pdf_path") is None

    checkpoint_state = app.get_state(config)
    assert checkpoint_state.next == ()


def test_sqlite_wal_mode_enabled(tmp_path):
    """Verify SQLite WAL journal mode and busy_timeout are active."""
    checkpoints_db = str(tmp_path / "checkpoints_wal.db")
    _ = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)

    conn = sqlite3.connect(checkpoints_db)
    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    conn.close()

    assert journal_mode.lower() == "wal"
    assert busy_timeout >= 5000
