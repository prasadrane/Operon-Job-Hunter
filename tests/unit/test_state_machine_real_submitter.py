"""Unit tests for LangGraph real submitter execution, HITL breakpoints, and graceful evaluation degradation."""

import importlib
import os
import sqlite3
from unittest.mock import MagicMock, patch
import pytest

_eval_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
RubricEvaluator = _eval_mod.RubricEvaluator

_sub_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
SubmitterEngine = _sub_mod.SubmitterEngine

from src.core.models import SubmissionReceipt
from src.pipeline.state_machine import (
    build_careergraph_pipeline,
    node_discover_and_evaluate,
    node_graphrag_tailor,
    node_submit_and_verify,
    route_evaluation,
)
from src.pipeline.state_schema import PipelineGraphState


def test_node_discover_and_evaluate_handles_evaluator_exception_with_warning():
    """Verify evaluator exceptions set an explicit evaluation warning flag and audit log."""
    state: PipelineGraphState = {
        "job_id": "test_job_err",
        "company": "Broken Co",
        "title": "SWE",
        "url": "https://boards.greenhouse.io/broken/jobs/1",
        "portal_type": "greenhouse",
    }

    with patch.object(RubricEvaluator, "evaluate", side_effect=ValueError("Corrupted HTML")):
        result = node_discover_and_evaluate(state)

    assert result["fit_score"] == 0.0
    assert result["evaluation_warning"] is True
    assert result["current_stage"] == "NEEDS_MANUAL_EVAL"
    assert any(log["event"] == "evaluation_warning" for log in result["audit_logs"])


def test_route_evaluation_routes_to_end_on_evaluation_warning():
    """Verify route_evaluation drops jobs with evaluation warnings or low fit scores."""
    state_warning: PipelineGraphState = {
        "fit_score": 0.0,
        "evaluation_warning": True,
    }
    assert route_evaluation(state_warning) == "end_node"

    state_good: PipelineGraphState = {
        "fit_score": 92.0,
        "is_ghost_job": False,
        "work_auth_blocker": False,
        "evaluation_warning": False,
    }
    assert route_evaluation(state_good) == "tailor_node"


def test_node_submit_and_verify_generates_staged_receipt_and_screenshot():
    """Verify node_submit_and_verify stages form submission with SubmitterEngine receipt."""
    state: PipelineGraphState = {
        "job_id": "job_gh_101",
        "company": "Databricks",
        "title": "Staff Platform Engineer",
        "url": "https://boards.greenhouse.io/databricks/jobs/101",
        "portal_type": "greenhouse",
        "resume_pdf_path": "data/artifacts/resume.pdf",
        "cover_letter_path": "data/artifacts/cover.pdf",
    }

    mock_receipt = SubmissionReceipt(
        job_id="job_gh_101",
        success=True,
        confirmation_id="REC-DATABRICKS-101",
        screenshot_path="data/artifacts/receipts/Databricks_101.png",
        portal_type="greenhouse",
    )

    with patch.object(SubmitterEngine, "submit", return_value=mock_receipt):
        result = node_submit_and_verify(state)

    assert result["submission_receipt_id"] == "REC-DATABRICKS-101"
    assert result["submission_screenshot_path"] == "data/artifacts/receipts/Databricks_101.png"
    assert result["current_stage"] == "SUBMITTED"
    assert any(log["event"] == "submitted" for log in result["audit_logs"])
