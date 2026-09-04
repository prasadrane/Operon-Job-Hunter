"""Application Agent (P5c): JOB_DISCOVERED -> batch dispatcher -> decisions.

Pipeline execution is NOT reimplemented here: BatchPipelineDispatcher.
process_single_job (src/pipeline/batch_dispatcher.py:45) already runs the
CareerGraphPipeline for one JobPosting and returns a normalized summary.
This agent adds the reactive layer: event guard, in-flight dedupe,
off-thread dispatch (P5a bus is synchronous), audit decisions, and
JOB_EVALUATED events. Resume past the HITL submit interrupt happens
ONLY through resume_submission(), mirroring cli/main.py:177.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Set

from src.agents.base import BaseAgent
from src.core.config import get_settings
from src.core.events import Event, EventType
from src.core.stages.stage_registry import can_handle

log = logging.getLogger("careergraph.agents.application")


class ApplicationAgent(BaseAgent):
    def __init__(self, name: str = "application_agent", dispatcher: Optional[Any] = None,
                 job_repo: Optional[Any] = None, concurrency: int = 2) -> None:
        super().__init__(name)
        self.handles = [EventType.JOB_DISCOVERED]
        self._dispatcher_obj = dispatcher
        self.job_repo = job_repo
        if self.job_repo is None:
            from src.core.db.repository import JobRepository
            self.job_repo = JobRepository()
        self.executor = ThreadPoolExecutor(max_workers=concurrency,
                                           thread_name_prefix="app-agent")
        self._inflight: Set[str] = set()

    @property
    def dispatcher(self):
        if self._dispatcher_obj is None:
            from src.pipeline.batch_dispatcher import BatchPipelineDispatcher
            self._dispatcher_obj = BatchPipelineDispatcher()
        return self._dispatcher_obj

    def on_event(self, event: Event) -> None:
        job_id = event.subject_id
        if not job_id or job_id in self._inflight:
            return
        job = self.job_repo.get_job(job_id)  # Optional[JobPosting] — verified model return
        if job is None:
            self.decide("skip", f"job {job_id} not found in repository", job_id=job_id)
            return
        state = self._state_from_job(job)
        if not can_handle("evaluation", state):
            self.decide("skip", "state missing evaluation inputs", job_id=job_id)
            return
        self._inflight.add(job_id)
        self.executor.submit(self._run_and_report, job_id, job)

    @staticmethod
    def _state_from_job(job) -> Dict[str, Any]:
        """JobPosting model -> PipelineGraphState fragment for can_handle gate."""
        return {"job_id": str(job.id), "url": job.url, "company": job.company,
                "title": job.title, "portal_type": job.portal_type or "generic"}

    def _run_and_report(self, job_id: str, job) -> None:
        try:
            self.decide("pipeline_start", "running eval/tailor via batch dispatcher",
                        job_id=job_id)
            result = self.dispatcher.process_single_job(job)
            fit = float(result.get("fit_score") or 0.0)
            status = str(result.get("status") or "FAILED")
            hitl_ready = bool(result.get("hitl_ready"))
            threshold = get_settings().min_fit_score
            if status == "SUCCESS" and fit >= threshold:
                self.decide("proceed",
                            f"SUCCESS fit {fit} >= {threshold}; staged for submit HITL"
                            if hitl_ready else
                            f"SUCCESS fit {fit} >= {threshold}; not staged",
                            job_id=job_id,
                            metadata={"fit_score": fit, "hitl_ready": hitl_ready})
            else:
                self.decide("hold",
                            f"status={status} fit={fit} threshold={threshold}",
                            job_id=job_id,
                            metadata={"fit_score": fit, "status": status,
                                      "error": result.get("error")})
            self._bus.publish(Event(event_type=EventType.JOB_EVALUATED,
                                    source=self.name, subject_id=job_id,
                                    payload={"fit_score": fit, "status": status,
                                             "hitl_ready": hitl_ready}))
        except Exception as exc:  # noqa: BLE001
            log.exception("dispatcher run failed for %s", job_id)
            self.decide("pipeline_error", str(exc), job_id=job_id)
        finally:
            self._inflight.discard(job_id)

    def resume_submission(self, job_id: str) -> Dict[str, Any]:
        """Explicit human-driven continue past the submit interrupt.
        Same LangGraph resume pattern as cli/main.py:177."""
        self.decide("resume_requested", "continue past submit interrupt",
                    job_id=job_id)
        from src.pipeline.state_machine import CareerGraphPipeline
        app = CareerGraphPipeline().app
        config = {"configurable": {"thread_id": str(job_id)}}
        result = app.invoke(None, config=config)
        self.decide("resumed", f"pipeline resumed; stage={result.get('current_stage')}",
                    job_id=job_id)
        return result
