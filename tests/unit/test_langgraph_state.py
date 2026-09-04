"""Unit tests for LangGraph PipelineGraphState schema, nodes, reducers, and routing."""
import operator
from unittest.mock import MagicMock, patch
import pytest

from src.pipeline.state_schema import PipelineGraphState
from src.pipeline.state_machine import (
    node_discover_and_evaluate,
    node_graphrag_tailor,
    node_submit_and_verify,
    route_evaluation,
)


def test_pipeline_graph_state_schema_structure():
    """Verify that PipelineGraphState defines all required fields, reducers, and metadata."""
    state: PipelineGraphState = {
        "job_id": "job_101",
        "company": "Stripe",
        "title": "Staff Engineer",
        "url": "https://stripe.com/jobs/101",
        "portal_type": "greenhouse",
        "fit_score": 92.0,
        "current_stage": "EVALUATED",
        "is_ghost_job": False,
        "work_auth_blocker": False,
        "resume_pdf_path": None,
        "cover_letter_path": None,
        "submission_receipt_id": None,
        "screenshot_path": None,
        "telegram_message_id": None,
        "qa_answers": {"relocation": "No"},
        "audit_logs": [{"event": "evaluated", "score": 92}],
        "errors": [],
        "evaluator_critiques": [],
    }

    assert state["job_id"] == "job_101"
    assert state["fit_score"] == 92.0
    assert state["qa_answers"] == {"relocation": "No"}
    assert "screenshot_path" in state
    assert "telegram_message_id" in state


def test_route_evaluation_conditional_branches():
    """Verify routing decisions based on fit score, ghost job flag, and work authorization."""
    # Passing candidate
    passing_state: PipelineGraphState = {
        "job_id": "job_pass",
        "company": "Google",
        "title": "Staff SWE",
        "url": "https://careers.google.com/jobs/1",
        "portal_type": "custom",
        "fit_score": 91.5,
        "current_stage": "EVALUATED",
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
    assert route_evaluation(passing_state) == "tailor_node"

    # Ghost job blocker
    ghost_state = {**passing_state, "is_ghost_job": True}
    assert route_evaluation(ghost_state) == "end_node"

    # Work auth blocker
    auth_state = {**passing_state, "work_auth_blocker": True}
    assert route_evaluation(auth_state) == "end_node"

    # Low fit score
    low_fit_state = {**passing_state, "fit_score": 79.0}
    assert route_evaluation(low_fit_state) == "end_node"


def test_pipeline_nodes_execution():
    """Verify individual node synchronous behaviors and output contracts."""
    base_state: PipelineGraphState = {
        "job_id": "job_sync_1",
        "company": "Meta",
        "title": "Senior Backend Engineer",
        "url": "https://metacareers.com/jobs/1",
        "portal_type": "custom",
        "fit_score": 0.0,
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

    # Evaluate node
    import importlib
    _eval_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
    RubricEvaluator = getattr(_eval_mod, "RubricEvaluator")
    mock_eval = MagicMock()
    mock_eval.fit_score = 92.0
    mock_eval.is_ghost_job = False
    mock_eval.work_auth_blocker = False

    with patch.object(RubricEvaluator, "evaluate", return_value=mock_eval):
        eval_res = node_discover_and_evaluate(base_state)
        assert eval_res["fit_score"] >= 40.0
        assert eval_res["current_stage"] == "EVALUATED"
        assert len(eval_res["audit_logs"]) == 1

    # Tailor node with deterministic mock
    _tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")
    ResumeGenerator = getattr(_tailor_mod, "ResumeGenerator")
    mock_artifacts = MagicMock()
    mock_artifacts.resume_pdf_path = "data/artifacts/job_sync_1_resume.pdf"
    mock_artifacts.cover_letter_path = "data/artifacts/job_sync_1_cover.txt"
    mock_artifacts.qa_answers = {"why_us": "Strong fit for Meta."}

    with patch.object(ResumeGenerator, "generate", return_value=mock_artifacts):
        tailor_res = node_graphrag_tailor(base_state)
        assert tailor_res["current_stage"] == "READY_FOR_HITL"
        assert "resume_pdf_path" in tailor_res
        assert tailor_res["resume_pdf_path"].endswith(".pdf")
        assert tailor_res["qa_answers"] == {"why_us": "Strong fit for Meta."}

    # Submit node
    submit_res = node_submit_and_verify(base_state)
    assert submit_res["current_stage"] == "SUBMITTED"
    assert submit_res["submission_receipt_id"] == "REC-job_sync_1"


def test_prune_transient_state_compacts_payload():
    """Verify that prune_transient_state strips large transient fields and keeps state compact (<10KB)."""
    from src.pipeline.state_schema import prune_transient_state
    import json

    bloated_state: PipelineGraphState = {
        "job_id": "job_prune_1",
        "company": "Amazon",
        "title": "Software Development Engineer II",
        "url": "https://amazon.jobs/1",
        "portal_type": "custom",
        "fit_score": 90.0,
        "current_stage": "SUBMITTING",
        "is_ghost_job": False,
        "work_auth_blocker": False,
        "resume_pdf_path": "/tmp/resume.pdf",
        "cover_letter_path": "/tmp/cover.pdf",
        "submission_receipt_id": "REC-1234",
        "screenshot_path": "/tmp/screen.png",
        "raw_dom_snapshot": "<html>" + ("<div>lots of DOM nodes</div>" * 5000) + "</html>",
        "transient_base64_image": "data:image/png;base64," + ("A" * 100000),
        "qa_answers": {"q1": "ans1"},
        "audit_logs": [{"event": f"event_{i}", "data": "x" * 100} for i in range(100)],
        "errors": ["error_1"],
        "evaluator_critiques": [{"critic": "ats", "feedback": "good"}],
    }

    pruned = prune_transient_state(bloated_state)

    # Transient bloated keys should be stripped
    assert "raw_dom_snapshot" not in pruned
    assert "transient_base64_image" not in pruned
    # Essential keys preserved
    assert pruned["job_id"] == "job_prune_1"
    assert pruned["resume_pdf_path"] == "/tmp/resume.pdf"
    # Serialized JSON size should be < 10 KB
    serialized_size = len(json.dumps(pruned, default=str).encode("utf-8"))
    assert serialized_size < 10240, f"Serialized size {serialized_size} exceeds 10KB budget!"

