"""Concurrent Batch LangGraph Dispatcher for parallel evaluation, tailoring, and HITL staging."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional

from src.core.db.repository import JobRepository
from src.core.models import JobPosting, JobStatus
from src.pipeline.state_machine import CareerGraphPipeline

log = logging.getLogger(__name__)


@dataclass
class BatchExecutionSummary:
    """Aggregate execution statistics for a concurrent pipeline batch."""

    total_jobs: int
    evaluated_count: int
    tailored_count: int
    hitl_ready_count: int
    rejected_count: int
    failed_count: int
    job_results: List[Dict[str, Any]] = field(default_factory=list)
    total_duration_sec: float = 0.0


class BatchPipelineDispatcher:
    """Thread-safe batch dispatcher executing multi-job LangGraph pipeline workflows concurrently."""

    def __init__(
        self,
        max_workers: int = 5,
        db_path: Optional[str] = None,
        checkpoints_db_path: str = "./data/checkpoints.db",
    ) -> None:
        self.max_workers = max_workers
        self.db_path = db_path
        self.checkpoints_db_path = checkpoints_db_path
        self.repository = JobRepository(db_path=db_path) if db_path else JobRepository()

    def process_single_job(
        self,
        job: JobPosting,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute the LangGraph pipeline for an isolated single job posting."""
        start_time = time.perf_counter()
        job_id = job.id
        pipeline = CareerGraphPipeline(checkpoints_db_path=self.checkpoints_db_path)

        initial_state = {
            "job_id": job.id,
            "company": job.company,
            "title": job.title,
            "url": job.url,
            "portal_type": job.portal_type or "generic",
            "description": job.description or "",
            "candidate_profile": user_profile or {},
            "audit_logs": [],
        }

        try:
            state = pipeline.run(initial_state, thread_id=job_id)
            eval_score = float(state.get("fit_score", 0.0) or state.get("evaluation_score", 0.0))
            is_eval_passed = bool(
                state.get("evaluation_passed", True)
                and not state.get("evaluation_warning", False)
                and not state.get("is_ghost_job", False)
                and not state.get("work_auth_blocker", False)
                and eval_score >= 85.0
            )
            tailoring_artifact = state.get("tailoring_artifact_id") or state.get("resume_artifact_id")
            hitl_status = state.get("hitl_status") or ("STAGED" if tailoring_artifact else None)

            status = "SUCCESS" if is_eval_passed else "REJECTED"
            duration = round(time.perf_counter() - start_time, 2)

            return {
                "job_id": job_id,
                "company": job.company,
                "title": job.title,
                "status": status,
                "fit_score": eval_score,
                "tailored": bool(tailoring_artifact),
                "tailoring_artifact_id": tailoring_artifact,
                "hitl_ready": bool(hitl_status or tailoring_artifact),
                "duration_sec": duration,
                "error": state.get("error_trace"),
            }
        except Exception as exc:
            log.error("Batch worker execution failed for job %s: %s", job_id, exc)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="batch",
                    component="batch_dispatcher",
                    error_type="BATCH_WORKER_ERROR",
                    message=f"Batch worker execution failed for job {job_id}: {exc}",
                    company=getattr(job, "company", None),
                    metadata={"job_id": job_id},
                )
            except Exception:
                pass
            return {
                "job_id": job_id,
                "company": job.company,
                "title": job.title,
                "status": "FAILED",
                "fit_score": 0.0,
                "tailored": False,
                "tailoring_artifact_id": None,
                "hitl_ready": False,
                "duration_sec": round(time.perf_counter() - start_time, 2),
                "error": str(exc),
            }

    def dispatch_batch(
        self,
        jobs: List[JobPosting],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> BatchExecutionSummary:
        """Process a list of job postings concurrently across the worker pool."""
        if not jobs:
            return BatchExecutionSummary(
                total_jobs=0,
                evaluated_count=0,
                tailored_count=0,
                hitl_ready_count=0,
                rejected_count=0,
                failed_count=0,
                job_results=[],
                total_duration_sec=0.0,
            )

        start_time = time.perf_counter()
        results: List[Dict[str, Any]] = []

        try:
            from src.interface.api.subagent_state import log_agent_event
            log_agent_event(f"[Dispatcher] 🚀 Spawning {self.max_workers} concurrent workers for batch of {len(jobs)} jobs...")
        except Exception:
            pass

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_job = {
                executor.submit(self.process_single_job, job, user_profile): job
                for job in jobs
            }
            for future in as_completed(future_to_job):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    job = future_to_job[future]
                    results.append({
                        "job_id": job.id,
                        "company": job.company,
                        "title": job.title,
                        "status": "FAILED",
                        "fit_score": 0.0,
                        "tailored": False,
                        "tailoring_artifact_id": None,
                        "hitl_ready": False,
                        "duration_sec": 0.0,
                        "error": str(exc),
                    })

        total_duration = round(time.perf_counter() - start_time, 2)
        evaluated_cnt = len(results)
        tailored_cnt = sum(1 for r in results if r.get("tailored"))
        hitl_cnt = sum(1 for r in results if r.get("hitl_ready"))
        rejected_cnt = sum(1 for r in results if r.get("status") == "REJECTED")
        failed_cnt = sum(1 for r in results if r.get("status") == "FAILED")

        try:
            from src.interface.api.subagent_state import log_agent_event
            log_agent_event(
                f"[Dispatcher] 🏁 Batch complete ({total_duration}s): {evaluated_cnt} evaluated, "
                f"{tailored_cnt} tailored, {hitl_cnt} HITL staged, {rejected_cnt} rejected."
            )
        except Exception:
            pass

        return BatchExecutionSummary(
            total_jobs=len(jobs),
            evaluated_count=evaluated_cnt,
            tailored_count=tailored_cnt,
            hitl_ready_count=hitl_cnt,
            rejected_count=rejected_cnt,
            failed_count=failed_cnt,
            job_results=results,
            total_duration_sec=total_duration,
        )

    def dispatch_pending_ledger(
        self,
        limit: int = 10,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> BatchExecutionSummary:
        """Pull top pending postings from the repository sorted by recency and dispatch batch."""
        pending_jobs = self.repository.get_jobs_by_status(JobStatus.DISCOVERED, limit=limit)
        return self.dispatch_batch(pending_jobs, user_profile=user_profile)
