"""Unit tests for distributed Celery task queue engine and worker pool simulation."""

import pytest
from unittest.mock import patch, MagicMock

from src.core.distributed.celery_app import celery_app, on_worker_process_init
from src.core.distributed.tasks import (
    execute_pipeline_task_sync,
    dispatch_batch_scan_task,
    dispatch_pipeline_job,
)


def test_celery_configuration_durability_flags():
    """Verify Celery app configuration has durability and prefetch flags set."""
    conf = celery_app.conf
    # Support both dict access and attribute access
    acks_late = conf.get("task_acks_late") if hasattr(conf, "get") else getattr(conf, "task_acks_late", None)
    reject_lost = conf.get("task_reject_on_worker_lost") if hasattr(conf, "get") else getattr(conf, "task_reject_on_worker_lost", None)
    prefetch = conf.get("worker_prefetch_multiplier") if hasattr(conf, "get") else getattr(conf, "worker_prefetch_multiplier", None)

    assert acks_late is True, "task_acks_late must be enabled for at-least-once delivery durability"
    assert reject_lost is True, "task_reject_on_worker_lost must be enabled to re-queue lost tasks"
    assert prefetch == 1, "worker_prefetch_multiplier must be 1 to prevent worker starvation/monopolization"


def test_worker_process_init_signal_db_isolation(tmp_path):
    """Verify worker_process_init signal handler re-initializes dual database pool for process isolation."""
    checkpoints = str(tmp_path / "checkpoints_worker.db")
    telemetry = str(tmp_path / "telemetry_worker.db")

    with patch("src.core.distributed.celery_app.init_dual_database_pool") as mock_init_pool:
        on_worker_process_init(checkpoints_path=checkpoints, telemetry_path=telemetry)
        mock_init_pool.assert_called_once_with(checkpoints_path=checkpoints, telemetry_path=telemetry)


def test_worker_process_init_defaults():
    """Verify worker_process_init with default arguments calls init_dual_database_pool."""
    with patch("src.core.distributed.celery_app.init_dual_database_pool") as mock_init_pool:
        on_worker_process_init()
        mock_init_pool.assert_called_once()


def test_execute_pipeline_task_sync_success():
    """Verify execute_pipeline_task_sync processes a job and returns execution receipt."""
    result = execute_pipeline_task_sync(
        job_id="job_remote_888",
        company="Airbnb",
        url="https://careers.airbnb.com/888",
    )
    assert result["status"] == "SUCCESS"
    assert result["job_id"] == "job_remote_888"
    assert result["company"] == "Airbnb"
    assert result["url"] == "https://careers.airbnb.com/888"
    assert "receipt_id" in result
    assert result["receipt_id"].startswith("REC-")
    assert result["state"] in ["COMPLETED", "PROCESSED", "SUBMITTED"]
    assert "timestamp" in result


def test_execute_pipeline_task_sync_invalid_input():
    """Verify execute_pipeline_task_sync handles missing/invalid parameters gracefully."""
    result = execute_pipeline_task_sync(job_id="", company="", url="")
    assert result["status"] == "FAILED"
    assert "error" in result


def test_dispatch_batch_scan_task():
    """Verify dispatch_batch_scan_task scans a list of job postings and returns batch metrics."""
    jobs = [
        {"job_id": "job_101", "company": "Stripe", "url": "https://stripe.com/jobs/101"},
        {"job_id": "job_102", "company": "Meta", "url": "https://meta.com/jobs/102"},
        {"job_id": "job_103", "company": "Apple", "url": "https://apple.com/jobs/103"},
    ]

    batch_result = dispatch_batch_scan_task(job_listings=jobs, batch_id="batch_test_001")
    assert batch_result["batch_id"] == "batch_test_001"
    assert batch_result["status"] == "SUCCESS"
    assert batch_result["total_jobs"] == 3
    assert batch_result["processed_jobs"] == 3
    assert batch_result["successful_jobs"] == 3
    assert batch_result["failed_jobs"] == 0
    assert len(batch_result["results"]) == 3
    assert all(r["status"] == "SUCCESS" for r in batch_result["results"])


def test_dispatch_batch_scan_task_with_partial_failures():
    """Verify dispatch_batch_scan_task tracks failed items and continues batch processing."""
    jobs = [
        {"job_id": "job_201", "company": "Google", "url": "https://careers.google.com/201"},
        {"job_id": "", "company": "BrokenCo", "url": ""},  # Invalid
        {"job_id": "job_203", "company": "Netflix", "url": "https://jobs.netflix.com/203"},
    ]

    batch_result = dispatch_batch_scan_task(job_listings=jobs)
    assert batch_result["status"] in ["PARTIAL_SUCCESS", "SUCCESS"]
    assert batch_result["total_jobs"] == 3
    assert batch_result["processed_jobs"] == 3
    assert batch_result["successful_jobs"] == 2
    assert batch_result["failed_jobs"] == 1


def test_dispatch_pipeline_job_delay_invocation():
    """Verify dispatch_pipeline_job can be executed directly or simulated via delay."""
    # Direct execution
    direct_res = dispatch_pipeline_job(
        job_id="job_async_999",
        company="Datadog",
        url="https://datadog.com/jobs/999",
    )
    assert direct_res["status"] == "SUCCESS"
    assert direct_res["job_id"] == "job_async_999"

    # Async delay simulation if available
    if hasattr(dispatch_pipeline_job, "delay"):
        async_result = dispatch_pipeline_job.delay(
            job_id="job_async_999",
            company="Datadog",
            url="https://datadog.com/jobs/999",
        )
        assert async_result is not None
        assert hasattr(async_result, "id") or isinstance(async_result, dict)
