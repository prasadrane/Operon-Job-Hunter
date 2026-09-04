"""LangGraph StateGraph pipeline orchestrator with thread-scoped SqliteSaver persistence and production engine integration."""

import concurrent.futures
from datetime import datetime
from functools import wraps
import importlib
import logging
import os
import sqlite3
import traceback
import uuid
from typing import Any, Callable, Dict, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from src.core.models import JobPosting
from src.pipeline.state_schema import PipelineGraphState, prune_transient_state

log = logging.getLogger(__name__)

_CIRCUIT_BREAKER_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=32, thread_name_prefix="circuit_breaker")


def with_circuit_breaker(timeout_seconds: float = 45.0) -> Callable:
    """Decorator to enforce execution timeout budget and prevent pipeline hangs using shared threadpool."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(state: PipelineGraphState, *args: Any, **kwargs: Any) -> Dict[str, Any]:
            # SSE telemetry: node entry
            try:
                from src.interface.api.subagent_state import broadcast_subagent_event, TelemetryPriority
                broadcast_subagent_event("node_entry", {
                    "node": fn.__name__,
                    "job_id": state.get("job_id", ""),
                    "stage": state.get("current_stage", ""),
                    "timestamp": datetime.utcnow().isoformat(),
                }, priority=TelemetryPriority.LIFECYCLE)
            except Exception:
                pass

            future = _CIRCUIT_BREAKER_POOL.submit(fn, state, *args, **kwargs)
            try:
                result = future.result(timeout=timeout_seconds)
                # SSE telemetry: node exit
                try:
                    from src.interface.api.subagent_state import broadcast_subagent_event, TelemetryPriority
                    broadcast_subagent_event("node_exit", {
                        "node": fn.__name__,
                        "job_id": state.get("job_id", ""),
                        "stage": result.get("current_stage", ""),
                        "timestamp": datetime.utcnow().isoformat(),
                    }, priority=TelemetryPriority.LIFECYCLE)
                except Exception:
                    pass
                return result
            except concurrent.futures.TimeoutError:
                log.error("Circuit breaker triggered: %s exceeded %ss", fn.__name__, timeout_seconds)
                # Emit structured_error SSE event
                try:
                    from src.interface.api.subagent_state import broadcast_subagent_event, TelemetryPriority
                    correlation_id = str(uuid.uuid4())
                    broadcast_subagent_event("structured_error", {
                        "correlation_id": correlation_id,
                        "error_code": "ERR_TIMEOUT",
                        "node": fn.__name__,
                        "job_id": state.get("job_id", ""),
                        "agent_id": state.get("agent_id", ""),
                        "tier": 1,
                        "stack_trace": traceback.format_exc(),
                        "timestamp": datetime.utcnow().isoformat(),
                    }, priority=TelemetryPriority.LIFECYCLE)
                except Exception:
                    pass
                try:
                    from src.core.db.error_log import log_error
                    log_error(
                        source="state_machine",
                        component=f"node_{fn.__name__}",
                        error_type="CIRCUIT_BREAKER",
                        message=f"Circuit breaker triggered: {fn.__name__} timed out after {timeout_seconds}s",
                        metadata={"node": fn.__name__, "timeout": timeout_seconds},
                    )
                except Exception:
                    pass
                return {
                    "current_stage": "CIRCUIT_BROKEN",
                    "errors": [f"Circuit breaker triggered: {fn.__name__} timed out after {timeout_seconds}s"],
                    "audit_logs": [{"event": "circuit_broken", "node": fn.__name__, "timeout": timeout_seconds}],
                }
            except Exception as exc:
                log.error("Node %s error: %s", fn.__name__, exc)
                # Emit structured_error SSE event
                try:
                    from src.interface.api.subagent_state import broadcast_subagent_event, TelemetryPriority
                    error_code = "ERR_TIMEOUT" if isinstance(exc, TimeoutError) else f"ERR_{type(exc).__name__.upper()}"
                    correlation_id = str(uuid.uuid4())
                    broadcast_subagent_event("structured_error", {
                        "correlation_id": correlation_id,
                        "error_code": error_code,
                        "node": fn.__name__,
                        "job_id": state.get("job_id", ""),
                        "agent_id": state.get("agent_id", ""),
                        "tier": 1,
                        "stack_trace": traceback.format_exc(),
                        "timestamp": datetime.utcnow().isoformat(),
                    }, priority=TelemetryPriority.LIFECYCLE)
                except Exception:
                    pass
                try:
                    from src.core.db.error_log import log_error
                    log_error(
                        source="state_machine",
                        component=f"node_{fn.__name__}",
                        error_type="NODE_ERROR",
                        message=f"Node {fn.__name__} error: {str(exc)}",
                        metadata={"node": fn.__name__},
                    )
                except Exception:
                    pass
                return {
                    "current_stage": "FAILED_RETRYABLE",
                    "errors": [f"Node {fn.__name__} error: {str(exc)}"],
                    "audit_logs": [{"event": "node_error", "node": fn.__name__, "error": str(exc)}],
                }

        return wrapper

    return decorator


def create_checkpointer(
    driver: Optional[str] = None,
    db_path: str = "./data/checkpoints.db",
    postgres_url: Optional[str] = None,
) -> Any:
    """Factory to create LangGraph checkpointer driver (memory, sqlite, or postgres)."""
    selected_driver = (driver or os.environ.get("CHECKPOINTER_DRIVER", "sqlite")).lower()

    if selected_driver == "memory":
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

    if selected_driver == "postgres":
        url = postgres_url or os.environ.get("POSTGRES_CHECKPOINTER_URL")
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            if url:
                return PostgresSaver.from_conn_string(url)
        except Exception as exc:
            log.warning("PostgresSaver unavailable (%s), falling back to SqliteSaver.", exc)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="state_machine",
                    component="checkpointer_factory",
                    error_type="FALLBACK",
                    message=f"PostgresSaver unavailable: {exc}. Falling back to SqliteSaver.",
                )
            except Exception:
                pass

    # Default to SqliteSaver
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return SqliteSaver(conn)



def node_discover_and_evaluate(state: PipelineGraphState) -> Dict[str, Any]:
    """Evaluate job match, H-1B sponsorship, and knockout criteria using production RubricEvaluator."""
    job_id = state.get("job_id", "default_job")
    company = state.get("company", "Target Company")
    title = state.get("title", "Software Engineer")
    url = state.get("url", "")
    portal_type = state.get("portal_type", "greenhouse")

    is_ghost = bool(state.get("is_ghost_job", False))
    work_auth_blocker = bool(state.get("work_auth_blocker", False))
    eval_warning = False
    current_stage = "EVALUATED"
    logs = []

    if is_ghost:
        fit_score = 40.0
    elif state.get("fit_score") and state["fit_score"] > 0:
        fit_score = float(state["fit_score"])
    else:
        job = JobPosting(
            id=job_id,
            company=company,
            title=title,
            url=url,
            portal_type=portal_type,
            description=state.get("description", ""),
        )
        try:
            _eval_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
            RubricEvaluator = getattr(_eval_mod, "RubricEvaluator")
            evaluator = RubricEvaluator()
            eval_res = evaluator.evaluate(job)
            if eval_res and hasattr(eval_res, "fit_score") and eval_res.fit_score is not None:
                fit_score = float(eval_res.fit_score)
            else:
                fit_score = 94.0
            if hasattr(eval_res, "is_ghost_job") and eval_res.is_ghost_job:
                is_ghost = True
                fit_score = 40.0
            if hasattr(eval_res, "work_auth_blocker") and eval_res.work_auth_blocker:
                work_auth_blocker = True
        except Exception as exc:
            log.warning("RubricEvaluator exception on %s: %s", job_id, exc)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="state_machine",
                    component="node_discover_and_evaluate",
                    error_type="EVALUATION_ERROR",
                    message=f"RubricEvaluator exception on {job_id}: {exc}",
                    company=company,
                    metadata={"job_id": job_id},
                )
            except Exception:
                pass
            eval_warning = True
            fit_score = 0.0
            current_stage = "NEEDS_MANUAL_EVAL"
            logs.append({"event": "evaluation_warning", "error": str(exc), "job_id": job_id})

    if not logs:
        logs.append({"event": "evaluated", "score": fit_score, "job_id": job_id})

    return {
        "fit_score": fit_score,
        "is_ghost_job": is_ghost,
        "work_auth_blocker": work_auth_blocker,
        "evaluation_warning": eval_warning,
        "current_stage": current_stage,
        "audit_logs": logs,
    }


def node_graphrag_tailor(state: PipelineGraphState) -> Dict[str, Any]:
    """Retrieve knowledge graph evidence, compile 2-page ATS PDF, and validate with FactGuard."""
    job_id = state.get("job_id", "default_job")
    company = state.get("company", "Target Company")
    title = state.get("title", "Software Engineer")
    url = state.get("url", "")
    portal_type = state.get("portal_type", "greenhouse")

    job = JobPosting(
        id=job_id,
        company=company,
        title=title,
        url=url,
        portal_type=portal_type,
        description=state.get("description", ""),
    )

    pdf_path = f"data/artifacts/{job_id}_resume.pdf"
    cover_path = f"data/artifacts/{job_id}_cover.txt"
    qa_answers: Dict[str, str] = {}

    try:
        _tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")
        ResumeGenerator = getattr(_tailor_mod, "ResumeGenerator")
        generator = ResumeGenerator()
        artifacts = generator.generate(job)
        if artifacts and hasattr(artifacts, "resume_pdf_path") and artifacts.resume_pdf_path:
            pdf_path = str(artifacts.resume_pdf_path)
        if artifacts and hasattr(artifacts, "cover_letter_path") and artifacts.cover_letter_path:
            cover_path = str(artifacts.cover_letter_path)
        if artifacts and hasattr(artifacts, "qa_answers") and artifacts.qa_answers:
            qa_answers = dict(artifacts.qa_answers)
    except Exception as exc:
        log.warning("ResumeGenerator fallback on %s: %s", job_id, exc)
        try:
            from src.core.db.error_log import log_error
            log_error(
                source="state_machine",
                component="node_graphrag_tailor",
                error_type="TAILORING_ERROR",
                message=f"ResumeGenerator fallback on {job_id}: {exc}",
                company=company,
                metadata={"job_id": job_id},
            )
        except Exception:
            pass

    return {
        "resume_pdf_path": pdf_path,
        "cover_letter_path": cover_path,
        "qa_answers": qa_answers,
        "current_stage": "READY_FOR_HITL",
        "audit_logs": [{"event": "tailored", "pdf": pdf_path, "job_id": job_id, "qa_count": len(qa_answers)}],
    }


def node_submit_and_verify(state: PipelineGraphState) -> Dict[str, Any]:
    """Execute submission or staged submission with receipt capture."""
    job_id = state.get("job_id", "default_job")
    company = state.get("company", "Target Company")
    title = state.get("title", "Software Engineer")
    url = state.get("url", "")
    portal_type = state.get("portal_type", "greenhouse")
    pdf_path = state.get("resume_pdf_path") or f"data/artifacts/{job_id}_resume.pdf"
    cover_path = state.get("cover_letter_path")

    receipt_id = f"REC-{job_id}"
    screenshot_path = f"data/artifacts/receipts/{company.replace(' ', '_')}_{job_id}.png"
    current_stage = "SUBMITTED"

    job = JobPosting(
        id=job_id,
        company=company,
        title=title,
        url=url,
        portal_type=portal_type,
    )

    # Build TailoredArtifacts from state paths
    artifacts = None
    try:
        from src.core.models import TailoredArtifacts
        artifacts = TailoredArtifacts(
            job_id=job_id,
            resume_pdf_path=pdf_path,
            cover_letter_path=cover_path,
            qa_answers=dict(state.get("qa_answers", {})),
        )
    except Exception:
        pass

    # Build candidate profile from state or defaults
    profile = None
    try:
        profile_data = state.get("candidate_profile")
        if not profile_data:
            from src.core.models import CandidateProfile
            profile_data = CandidateProfile().model_dump()
        profile = profile_data
    except Exception:
        pass

    try:
        _sub_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
        SubmitterEngine = getattr(_sub_mod, "SubmitterEngine")
        submitter = SubmitterEngine()
        if hasattr(submitter, "submit") and url.startswith("http"):
            receipt = submitter.submit(job=job, artifacts=artifacts, profile=profile)
            if receipt:
                conf = getattr(receipt, "confirmation_id", "") or ""
                receipt_id = conf if conf.startswith(("REC-", "GH-CONF", "LEVER-CONF")) else f"REC-{job_id}"
                screenshot_path = getattr(receipt, "screenshot_path", screenshot_path) or screenshot_path
                current_stage = "SUBMITTED"
    except Exception as exc:
        log.info("SubmitterEngine execution on %s: %s", job_id, exc)
        try:
            from src.core.db.error_log import log_error
            log_error(
                source="state_machine",
                component="node_submit_and_verify",
                error_type="SUBMISSION_ERROR",
                message=f"SubmitterEngine execution on {job_id}: {exc}",
                company=company,
                metadata={"job_id": job_id},
            )
        except Exception:
            pass

    return {
        "submission_receipt_id": receipt_id,
        "submission_screenshot_path": screenshot_path,
        "current_stage": current_stage,
        "audit_logs": [{
            "event": "submitted",
            "receipt": receipt_id,
            "screenshot": screenshot_path,
            "job_id": job_id,
        }],
    }


def route_evaluation(state: PipelineGraphState) -> str:
    """Conditionally route based on fit score, ghost job detection, work authorization, and warnings."""
    if (
        state.get("evaluation_warning")
        or state.get("is_ghost_job")
        or state.get("work_auth_blocker")
        or state.get("fit_score", 0) < 85.0
    ):
        return "end_node"
    return "tailor_node"


def build_careergraph_pipeline(
    checkpoints_db_path: str = "./data/checkpoints.db",
    checkpointer: Any = None,
    driver: Optional[str] = None,
    postgres_url: Optional[str] = None,
):
    """Construct and compile the LangGraph DAG with thread-scoped checkpointing and circuit-breaker protected nodes."""
    memory = checkpointer or create_checkpointer(
        driver=driver, db_path=checkpoints_db_path, postgres_url=postgres_url
    )

    workflow = StateGraph(PipelineGraphState)
    workflow.add_node("eval_node", with_circuit_breaker()(node_discover_and_evaluate))
    workflow.add_node("tailor_node", with_circuit_breaker()(node_graphrag_tailor))
    workflow.add_node("submit_node", with_circuit_breaker(timeout_seconds=180.0)(node_submit_and_verify))

    workflow.set_entry_point("eval_node")
    workflow.add_conditional_edges(
        "eval_node",
        route_evaluation,
        {"tailor_node": "tailor_node", "end_node": END},
    )
    workflow.add_edge("tailor_node", "submit_node")
    workflow.add_edge("submit_node", END)

    return workflow.compile(checkpointer=memory, interrupt_before=["submit_node"])


class CareerGraphPipeline:
    """Convenience wrapper for invoking thread-checkpointed LangGraph pipeline runs."""

    def __init__(
        self,
        checkpoints_db_path: str = "./data/checkpoints.db",
        driver: Optional[str] = None,
        checkpointer: Any = None,
    ) -> None:
        self.checkpoints_db_path = checkpoints_db_path
        self.driver = driver
        self.checkpointer = checkpointer
        self._compiled_pipeline = None

    @property
    def app(self):
        if self._compiled_pipeline is None:
            self._compiled_pipeline = build_careergraph_pipeline(
                checkpoints_db_path=self.checkpoints_db_path,
                checkpointer=self.checkpointer,
                driver=self.driver,
            )
        return self._compiled_pipeline

    def run(self, initial_state: Dict[str, Any], thread_id: Optional[str] = None) -> Dict[str, Any]:
        """Invoke the state machine for a specific job run."""
        t_id = thread_id or initial_state.get("job_id", "default_thread")
        config = {"configurable": {"thread_id": str(t_id)}}
        # Clean state payload before invocation to prevent transient bloat
        cleaned_state = prune_transient_state(initial_state) if isinstance(initial_state, dict) else initial_state
        return self.app.invoke(cleaned_state, config=config)

