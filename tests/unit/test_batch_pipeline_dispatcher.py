"""Unit tests for Concurrent Batch LangGraph Dispatcher."""

from datetime import datetime, timezone, timedelta
import importlib
from unittest.mock import MagicMock, patch
import pytest

from src.core.models import JobPosting, JobStatus, EvaluationResult

_batch_mod = importlib.import_module("src.pipeline.batch_dispatcher")
BatchPipelineDispatcher = _batch_mod.BatchPipelineDispatcher
BatchExecutionSummary = _batch_mod.BatchExecutionSummary


def test_batch_dispatcher_initialization():
    """Verify default initialization parameters."""
    dispatcher = BatchPipelineDispatcher(max_workers=4)
    assert dispatcher.max_workers == 4
    assert dispatcher.repository is not None


def test_process_single_job_success():
    """Verify single job execution isolates state and records success."""
    dispatcher = BatchPipelineDispatcher(max_workers=2)

    job = JobPosting(
        id="job_batch_101",
        company="Stripe",
        title="Senior Backend Engineer",
        url="https://stripe.com/jobs/101",
        posted_at=datetime.now(timezone.utc),
    )

    mock_state = {
        "job_id": "job_batch_101",
        "fit_score": 88.0,
        "evaluation_passed": True,
        "tailoring_artifact_id": "art_101",
        "hitl_status": "STAGED",
        "submission_success": False,
        "error_trace": None,
    }

    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = mock_state

    with patch("src.pipeline.batch_dispatcher.CareerGraphPipeline", return_value=mock_pipeline):
        result = dispatcher.process_single_job(job)

    assert result["job_id"] == "job_batch_101"
    assert result["status"] == "SUCCESS"
    assert result["fit_score"] == 88.0
    assert result["tailored"] is True
    assert result["hitl_ready"] is True


def test_process_single_job_handles_rejection():
    """Verify single job handles evaluation rejection cleanly."""
    dispatcher = BatchPipelineDispatcher(max_workers=2)

    job = JobPosting(
        id="job_batch_reject",
        company="Other Corp",
        title="Software Intern",
        url="https://other.com/jobs/99",
        posted_at=datetime.now(timezone.utc),
    )

    mock_state = {
        "job_id": "job_batch_reject",
        "fit_score": 25.0,
        "evaluation_passed": False,
        "tailoring_artifact_id": None,
        "hitl_status": None,
        "submission_success": False,
        "error_trace": "Candidate disqualified from intern role.",
    }

    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = mock_state

    with patch("src.pipeline.batch_dispatcher.CareerGraphPipeline", return_value=mock_pipeline):
        result = dispatcher.process_single_job(job)

    assert result["job_id"] == "job_batch_reject"
    assert result["status"] == "REJECTED"
    assert result["tailored"] is False


def test_dispatch_batch_concurrent_execution():
    """Verify concurrent batch processes all jobs and calculates aggregate summary."""
    dispatcher = BatchPipelineDispatcher(max_workers=3)

    jobs = [
        JobPosting(id=f"job_concurrent_{i}", company=f"Company {i}", title="SWE", url=f"https://co{i}.com")
        for i in range(5)
    ]

    def mock_process(job, user_profile=None):
        return {
            "job_id": job.id,
            "status": "SUCCESS" if job.id != "job_concurrent_4" else "REJECTED",
            "fit_score": 85.0 if job.id != "job_concurrent_4" else 30.0,
            "tailored": job.id != "job_concurrent_4",
            "hitl_ready": job.id != "job_concurrent_4",
            "error": None,
        }

    with patch.object(dispatcher, "process_single_job", side_effect=mock_process):
        summary = dispatcher.dispatch_batch(jobs)

    assert isinstance(summary, BatchExecutionSummary)
    assert summary.total_jobs == 5
    assert summary.tailored_count == 4
    assert summary.rejected_count == 1
    assert summary.hitl_ready_count == 4
    assert len(summary.job_results) == 5


def test_dispatch_pending_ledger():
    """Verify dispatcher pulls top pending jobs from repository."""
    dispatcher = BatchPipelineDispatcher(max_workers=2)
    mock_jobs = [
        JobPosting(id="job_ledger_1", company="A", title="SWE", url="https://a.com"),
        JobPosting(id="job_ledger_2", company="B", title="SWE", url="https://b.com"),
    ]

    with patch.object(dispatcher.repository, "get_jobs_by_status", return_value=mock_jobs):
        with patch.object(dispatcher, "dispatch_batch") as mock_batch:
            mock_batch.return_value = BatchExecutionSummary(
                total_jobs=2, evaluated_count=2, tailored_count=2, hitl_ready_count=2, rejected_count=0, failed_count=0, job_results=[], total_duration_sec=1.5
            )
            summary = dispatcher.dispatch_pending_ledger(limit=2)

    assert summary.total_jobs == 2
    mock_batch.assert_called_once_with(mock_jobs, user_profile=None)
