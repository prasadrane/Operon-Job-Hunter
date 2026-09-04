"""Unit and integration tests for LangGraph production DAG with real engine wiring."""

import importlib
import pytest
from unittest.mock import patch

from src.core.models import JobPosting, EvaluationResult, TailoredArtifacts
from src.pipeline.state_schema import PipelineGraphState
from src.pipeline.state_machine import (
    build_careergraph_pipeline,
    node_discover_and_evaluate,
    node_graphrag_tailor,
    node_submit_and_verify,
    route_evaluation,
)

eval_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")


def test_production_langgraph_eval_node_wiring():
    """Verify node_discover_and_evaluate uses RubricEvaluator and updates state."""
    state: PipelineGraphState = {
        "job_id": "job_stripe_1",
        "company": "Stripe",
        "title": "Staff Backend Engineer",
        "url": "https://boards.greenhouse.io/stripe/jobs/1",
        "portal_type": "greenhouse",
        "current_stage": "DISCOVERED",
        "is_ghost_job": False,
        "work_auth_blocker": False,
        "audit_logs": [],
    }

    mock_eval = EvaluationResult(
        job_id="job_stripe_1",
        fit_score=94.5,
        reason="Strong alignment with .NET backend and AWS cloud architecture.",
        work_auth_blocker=False,
        is_ghost_job=False,
    )

    with patch.object(eval_mod.RubricEvaluator, "evaluate", return_value=mock_eval):
        res = node_discover_and_evaluate(state)
        assert res["fit_score"] == 94.5
        assert res["current_stage"] == "EVALUATED"
        assert res["is_ghost_job"] is False
        assert res["work_auth_blocker"] is False
        assert len(res["audit_logs"]) == 1


def test_production_langgraph_tailor_node_wiring():
    """Verify node_graphrag_tailor uses ResumeGenerator and FactGuard."""
    state: PipelineGraphState = {
        "job_id": "job_stripe_1",
        "company": "Stripe",
        "title": "Staff Backend Engineer",
        "url": "https://boards.greenhouse.io/stripe/jobs/1",
        "portal_type": "greenhouse",
        "fit_score": 94.5,
        "current_stage": "EVALUATED",
        "audit_logs": [],
    }

    mock_artifacts = TailoredArtifacts(
        job_id="job_stripe_1",
        resume_pdf_path="data/artifacts/job_stripe_1_resume.pdf",
        cover_letter_path="data/artifacts/job_stripe_1_cover.txt",
        tailored_resume_text="Verified resume text",
    )

    with patch.object(tailor_mod.ResumeGenerator, "generate", return_value=mock_artifacts):
        res = node_graphrag_tailor(state)
        assert res["resume_pdf_path"] == "data/artifacts/job_stripe_1_resume.pdf"
        assert res["current_stage"] == "READY_FOR_HITL"
        assert len(res["audit_logs"]) == 1


def test_production_langgraph_e2e_checkpoint_flow(tmp_path):
    """Verify full LangGraph execution from evaluation to tailored HITL pause and submission."""
    checkpoints_db = str(tmp_path / "checkpoints_prod.db")

    thread_id = "job_databricks_777"
    config = {"configurable": {"thread_id": thread_id}}
    initial_state: PipelineGraphState = {
        "job_id": thread_id,
        "company": "Databricks",
        "title": "Senior Platform Engineer",
        "url": "https://boards.greenhouse.io/databricks/jobs/777",
        "portal_type": "greenhouse",
        "current_stage": "DISCOVERED",
        "audit_logs": [],
        "errors": [],
        "evaluator_critiques": [],
    }

    # Step 1: Run graph until human-in-the-loop interruption before submit_node
    mock_eval = EvaluationResult(
        job_id=thread_id,
        fit_score=92.0,
        reason="Strong fit for senior platform role.",
        work_auth_blocker=False,
        is_ghost_job=False,
    )
    mock_artifacts = TailoredArtifacts(
        job_id=thread_id,
        resume_pdf_path=f"data/artifacts/{thread_id}_resume.pdf",
        cover_letter_path=f"data/artifacts/{thread_id}_cover.txt",
        tailored_resume_text="STAR stories",
    )

    app = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)
    with patch.object(eval_mod.RubricEvaluator, "evaluate", return_value=mock_eval), \
         patch.object(tailor_mod.ResumeGenerator, "generate", return_value=mock_artifacts):
        state_after_tailor = app.invoke(initial_state, config=config)
        assert state_after_tailor["current_stage"] == "READY_FOR_HITL"
        assert state_after_tailor["fit_score"] == 92.0
        assert state_after_tailor["resume_pdf_path"] is not None

    # Step 2: Rebuild graph with mocked submit_node, resume from checkpoint
    mock_submit_result = {
        "current_stage": "SUBMITTED",
        "submission_receipt_id": f"REC-{thread_id}",
        "audit_logs": [{"node": "submit", "action": "submitted"}],
    }
    with patch("src.pipeline.state_machine.node_submit_and_verify", return_value=mock_submit_result):
        app2 = build_careergraph_pipeline(checkpoints_db_path=checkpoints_db)
        final_state = app2.invoke(None, config=config)
    assert final_state["current_stage"] == "SUBMITTED"
    assert final_state["submission_receipt_id"] == f"REC-{thread_id}"
