"""Browser Use integration for CareerGraph Stage 4 submission (Tier 2).

Provides:
- SubmissionTask: Pydantic input model for a Browser Use submission task
- SubmissionResult: Pydantic output model with audit trail
- CareerGraphController: Custom Browser Use controller with domain actions
- BrowserUseSubmissionAgent: Main wrapper around browser_use.Agent

This is the T2 tier in the 3-tier submission routing:
  T1: FastPath (deterministic, zero LLM cost)
  T2: Browser Use (LLM-driven, handles novel DOMs)
  T3: WebSurfer (rule-based fallback)

Browser Use is used when T1 FastPath fails or portal is unknown. It leverages
LLM-driven browser automation via CDP to handle dynamic/novel application forms.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from src.core.config import get_settings
from .submission_audit import AuditEntry, log_audit

logger = logging.getLogger(__name__)


# ── Input Schema ──────────────────────────────────────────────────────────────


class SubmissionTask(BaseModel):
    """Input contract for a Browser Use submission task."""

    job_url: str = Field(..., description="Full URL to the job application page")
    company: str = Field(..., description="Company name")
    title: str = Field(..., description="Job title")
    portal_type: str = Field(default="unknown", description="ATS platform identifier")
    job_id: Optional[str] = Field(None, description="Job posting ID")

    # Candidate data
    profile: Dict[str, Any] = Field(..., description="Candidate profile fields")
    resume_pdf_path: Optional[str] = Field(None, description="Absolute path to tailored resume PDF")
    cover_letter_path: Optional[str] = Field(None, description="Absolute path to cover letter PDF")

    # Credentials (from CredentialVault, NOT persisted)
    credentials: Optional[Dict[str, str]] = Field(None, description="Login credentials if needed")

    # Job context for question answering
    job_description: Optional[str] = Field(None, description="Full JD for question answering")
    star_narratives: Optional[List[Dict[str, Any]]] = Field(None, description="STAR narratives from GraphRAG")

    # Behavior controls
    use_vision: str = Field(default="auto", description="auto|true|false")
    max_steps: int = Field(default=30, description="Maximum agent steps before giving up")
    timeout_seconds: int = Field(default=90, description="Per-task timeout")


# ── Output Schema ─────────────────────────────────────────────────────────────


class SubmissionResult(BaseModel):
    """Structured output from Browser Use submission."""

    success: bool = Field(..., description="Whether submission completed")
    confirmation_id: Optional[str] = Field(None, description="Receipt/confirmation code")
    screenshot_path: Optional[str] = Field(None, description="Path to final screenshot")
    steps_taken: int = Field(default=0, description="Number of agent steps executed")
    tokens_used: int = Field(default=0, description="Approximate token consumption")
    duration_seconds: float = Field(default=0.0, description="Wall-clock duration")
    error_message: Optional[str] = Field(None, description="Error description on failure")
    filled_fields: Dict[str, Any] = Field(default_factory=dict, description="Fields that were filled")
    questions_answered: int = Field(default=0, description="Custom questions answered")
    tier_used: str = Field(default="T2", description="Which engine handled it: T1/T2/T3")
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list, description="Step-by-step audit log")


# ── Error Types ───────────────────────────────────────────────────────────────


class SubmissionError(Exception):
    """Base error for submission pipeline."""
    pass


class AuthError(SubmissionError):
    """Authentication/session validation failed."""
    retryable = True


class CaptchaError(SubmissionError):
    """CAPTCHA could not be solved within timeout."""
    retryable = False


class TierExhaustedError(SubmissionError):
    """All three tiers (T1/T2/T3) failed."""
    retryable = False


# ── Custom Controller ─────────────────────────────────────────────────────────


class CareerGraphController:
    """Custom Browser Use controller with CareerGraph domain actions.

    Wraps browser_use.Controller and registers domain-specific actions:
    - upload_resume: Upload candidate's resume PDF to file input
    - answer_question: Generate answer for screening question using QA synthesizer
    - fill_profile: Hint action for mapping form fields to candidate data

    Hooks into BrowserUseSubmissionAgent's auditor for observability.
    """

    def __init__(
        self,
        profile: dict,
        job_context: dict,
        qa_synthesizer: Optional[Any] = None,
        auditor_callback: Optional[Callable[[AuditEntry], None]] = None,
        submission_id: Optional[str] = None,
    ):
        self.profile = profile
        self.job_context = job_context
        self.qa_synthesizer = qa_synthesizer
        self.auditor_callback = auditor_callback
        self.submission_id = submission_id or str(uuid.uuid4())
        self._step_counter = 0
        self._controller = None  # Lazy init to avoid import at module load

    def _get_controller(self):
        """Lazy-initialize the browser_use.Controller to avoid import errors when browser-use not installed."""
        if self._controller is None:
            from browser_use import Controller
            self._controller = Controller()
            self._register_actions()
        return self._controller

    def _audit(self, action_type: str, target: str, success: bool, duration_ms: Optional[float] = None,
               error_detail: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """Record an audit entry via callback or log_audit."""
        self._step_counter += 1
        entry_data = {
            "submission_id": self.submission_id,
            "action_type": action_type,
            "target": target,
            "success": success,
            "job_id": self.job_context.get("job_id"),
            "company": self.job_context.get("company"),
            "portal_type": self.job_context.get("portal_type"),
            "tier": "T2",
            "step_index": self._step_counter,
            "duration_ms": duration_ms,
            "error_detail": error_detail,
            "metadata": metadata or {},
        }

        if self.auditor_callback:
            try:
                self.auditor_callback(AuditEntry(**entry_data))
            except Exception as exc:
                logger.warning("Auditor callback failed: %s", exc)
        else:
            log_audit(**entry_data)

    def _register_actions(self):
        """Register all custom actions with the controller."""

        @self._controller.action("Upload resume PDF to file input")
        async def upload_resume(file_path: str, browser_context=None):
            """Upload the candidate's resume PDF to the current file input."""
            start = time.monotonic()
            if not file_path or not os.path.exists(file_path):
                dur = (time.monotonic() - start) * 1000
                self._audit("upload_file", file_path or "none", False, dur,
                            error_detail=f"Resume file not found: {file_path}")
                return f"Resume file not found: {file_path}"

            try:
                page = await browser_context.get_current_page()
                file_input = await page.query_selector('input[type="file"]')
                if file_input:
                    await file_input.set_input_files(file_path)
                    dur = (time.monotonic() - start) * 1000
                    self._audit("upload_file", 'input[type="file"]', True, dur,
                                metadata={"filename": os.path.basename(file_path)})
                    return f"Uploaded resume: {os.path.basename(file_path)}"
                else:
                    dur = (time.monotonic() - start) * 1000
                    self._audit("upload_file", 'input[type="file"]', False, dur,
                                error_detail="No file input found on page")
                    return "No file input found"
            except Exception as exc:
                dur = (time.monotonic() - start) * 1000
                self._audit("upload_file", 'input[type="file"]', False, dur, error_detail=str(exc))
                return f"Upload failed: {exc}"

        @self._controller.action("Answer application screening question")
        async def answer_question(question: str) -> str:
            """Generate an answer for a custom application question using
            the candidate's profile, resume, and STAR narratives."""
            start = time.monotonic()
            if self.qa_synthesizer:
                try:
                    answer = self.qa_synthesizer.synthesize_answer(
                        question=question,
                        profile=self.profile,
                        job_context=self.job_context,
                    )
                    dur = (time.monotonic() - start) * 1000
                    self._audit("answer_question", question[:100], True, dur)
                    return answer
                except Exception as exc:
                    dur = (time.monotonic() - start) * 1000
                    self._audit("answer_question", question[:100], False, dur, error_detail=str(exc))
                    return f"Unable to answer: {exc}"
            dur = (time.monotonic() - start) * 1000
            self._audit("answer_question", question[:100], False, dur,
                        error_detail="No QA synthesizer available")
            return "Unable to answer — no synthesizer available"

        @self._controller.action("Fill candidate profile field")
        async def fill_profile_field(field_name: str, value: str) -> str:
            """Fill a specific profile field. Use this when you identify a form
            field that matches candidate data (name, email, phone, etc)."""
            start = time.monotonic()
            dur = (time.monotonic() - start) * 1000
            self._audit("fill_field", field_name, True, dur,
                        metadata={"value_length": len(value)})
            return f"Field '{field_name}' mapped to value (use type action to fill)"

    @property
    def controller(self):
        """Access the underlying browser_use.Controller."""
        return self._get_controller()


# ── Main Agent Wrapper ────────────────────────────────────────────────────────


class BrowserUseSubmissionAgent:
    """Wraps browser_use.Agent for CareerGraph submission tasks.

    This is the T2 tier engine. It uses LLM-driven browser automation to handle
    novel/dynamic application forms that T1 FastPath cannot handle.

    Features:
    - Structured input/output via Pydantic models
    - Audit trail for every major action (via SubmissionAuditor)
    - Configurable LLM (default: Alibaba Qwen via OpenAI-compatible endpoint)
    - Fallback LLM chain (Alibaba → Gemini)
    - Kill switch via SUBMISSION_BROWSER_USE_ENABLED env var
    - Timeout handling with inner per-tier budget
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        fallback_llm: Optional[Any] = None,
        qa_synthesizer: Optional[Any] = None,
    ):
        settings = get_settings()
        self.enabled = settings.browser_use_enabled
        self.use_vision = settings.browser_use_vision
        self.max_steps = settings.browser_use_max_steps
        self.max_failures = settings.browser_use_max_failures
        self.timeout_seconds = settings.browser_use_timeout_seconds
        self.qa_synthesizer = qa_synthesizer

        # Build LLM instances if not provided
        self.llm = llm or self._build_llm(
            provider=settings.primary_llm_provider,
            model=settings.browser_use_model,
            api_key=settings.alibaba_api_key,
            base_url=settings.alibaba_base_url,
        )
        self.fallback_llm = fallback_llm or self._build_fallback_llm(
            provider=settings.browser_use_fallback_provider,
            model=settings.browser_use_fallback_model,
            api_key=settings.gemini_api_key,
        )

    def _build_llm(self, provider: str, model: str, api_key: Optional[str], base_url: Optional[str]):
        """Build a LangChain-compatible LLM instance for Browser Use."""
        try:
            from langchain_openai import ChatOpenAI
            # Use OpenAI-compatible endpoint (Alibaba, OpenRouter, etc.)
            return ChatOpenAI(
                model=model,
                api_key=api_key or "dummy",
                base_url=base_url,
                temperature=0.1,
                max_retries=2,
            )
        except ImportError:
            logger.warning("langchain_openai not available, Browser Use will not function")
            return None

    def _build_fallback_llm(self, provider: str, model: str, api_key: Optional[str]):
        """Build fallback LLM (e.g., Gemini)."""
        if provider == "gemini" and api_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=model,
                    google_api_key=api_key,
                    temperature=0.1,
                )
            except ImportError:
                logger.warning("langchain_google_genai not available for fallback LLM")
        return None

    async def submit(self, task: SubmissionTask) -> SubmissionResult:
        """Execute a submission task via Browser Use Agent.

        Returns structured SubmissionResult with audit trail.
        """
        if not self.enabled:
            return SubmissionResult(
                success=False,
                error_message="Browser Use disabled via config (SUBMISSION_BROWSER_USE_ENABLED=false)",
                tier_used="T2",
            )

        if self.llm is None:
            return SubmissionResult(
                success=False,
                error_message="LLM not configured for Browser Use",
                tier_used="T2",
            )

        # Build controller with task-specific context
        submission_id = str(uuid.uuid4())
        controller_wrapper = CareerGraphController(
            profile=task.profile,
            job_context={
                "job_id": task.job_id,
                "company": task.company,
                "title": task.title,
                "url": task.job_url,
                "portal_type": task.portal_type,
                "description": task.job_description,
                "star_narratives": task.star_narratives,
            },
            qa_synthesizer=self.qa_synthesizer,
            submission_id=submission_id,
        )

        # Compose task prompt
        task_prompt = self._build_task_prompt(task)

        # Create agent
        try:
            from browser_use import Agent
        except ImportError:
            return SubmissionResult(
                success=False,
                error_message="browser-use package not installed",
                tier_used="T2",
            )

        agent = Agent(
            task=task_prompt,
            llm=self.llm,
            controller=controller_wrapper.controller,
            use_vision=task.use_vision if task.use_vision != "auto" else "auto",
            max_failures=self.max_failures,
            fallback_llm=self.fallback_llm,
        )

        # Execute with timeout
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                agent.run(),
                timeout=task.timeout_seconds,
            )
            duration = time.monotonic() - start

            # Extract structured result
            return self._extract_result(result, duration, submission_id, task)

        except asyncio.TimeoutError:
            duration = time.monotonic() - start
            log_audit(
                submission_id=submission_id,
                action_type="submit",
                target=task.job_url,
                success=False,
                job_id=task.job_id,
                company=task.company,
                portal_type=task.portal_type,
                tier="T2",
                duration_ms=duration * 1000,
                error_detail=f"Browser Use timed out after {task.timeout_seconds}s",
            )
            return SubmissionResult(
                success=False,
                error_message=f"Browser Use timed out after {task.timeout_seconds}s",
                duration_seconds=duration,
                tier_used="T2",
            )
        except Exception as e:
            duration = time.monotonic() - start
            logger.exception("Browser Use submission failed: %s", e)
            log_audit(
                submission_id=submission_id,
                action_type="submit",
                target=task.job_url,
                success=False,
                job_id=task.job_id,
                company=task.company,
                portal_type=task.portal_type,
                tier="T2",
                duration_ms=duration * 1000,
                error_detail=str(e),
            )
            return SubmissionResult(
                success=False,
                error_message=str(e),
                duration_seconds=duration,
                tier_used="T2",
            )

    def _build_task_prompt(self, task: SubmissionTask) -> str:
        """Compose natural language task description for the agent."""
        resume_line = f"4. Upload the resume PDF from: {task.resume_pdf_path}" if task.resume_pdf_path else "4. Upload the resume PDF if a file input is found"
        login_line = "2. If login is required, use the provided credentials" if task.credentials else "2. If login is required, report failure (no credentials provided)"

        return f"""Go to {task.job_url} and complete the job application for
{task.title} at {task.company}.

Steps:
1. Navigate to the application form
{login_line}
3. Fill in all personal information fields using the candidate profile
{resume_line}
5. Answer any screening questions using the job context
6. Review the application
7. Click submit
8. Wait for confirmation and extract the confirmation/receipt number

Important:
- Do NOT submit if any required field is empty
- If a CAPTCHA appears, wait for it to be solved
- Take a screenshot of the confirmation page
- Report the confirmation number if visible"""

    def _extract_result(
        self,
        agent_result: Any,
        duration: float,
        submission_id: str,
        task: SubmissionTask,
    ) -> SubmissionResult:
        """Extract SubmissionResult from Browser Use agent result."""
        # Browser Use Agent returns a Result object with .final_result()
        # We need to extract structured data from it
        success = False
        confirmation_id = None
        steps_taken = 0
        tokens_used = 0
        filled_fields = {}
        questions_answered = 0
        audit_trail = []

        try:
            # Extract from result object
            if hasattr(agent_result, "final_result"):
                final = agent_result.final_result()
                if final and isinstance(final, dict):
                    success = final.get("success", False)
                    confirmation_id = final.get("confirmation_id")
                    filled_fields = final.get("filled_fields", {})
                    questions_answered = final.get("questions_answered", 0)

            if hasattr(agent_result, "steps"):
                steps_taken = len(agent_result.steps()) if callable(agent_result.steps) else 0

            # Build audit trail from auditor
            from .submission_audit import SubmissionAuditor
            auditor = SubmissionAuditor()
            entries = auditor.get_entries_by_submission(submission_id)
            audit_trail = [e.to_dict() for e in entries]

            # Log final submit action
            log_audit(
                submission_id=submission_id,
                action_type="submit",
                target=task.job_url,
                success=success,
                job_id=task.job_id,
                company=task.company,
                portal_type=task.portal_type,
                tier="T2",
                duration_ms=duration * 1000,
                metadata={"steps_taken": steps_taken, "confirmation_id": confirmation_id},
            )

        except Exception as exc:
            logger.warning("Failed to extract result from Browser Use: %s", exc)

        return SubmissionResult(
            success=success,
            confirmation_id=confirmation_id,
            steps_taken=steps_taken,
            tokens_used=tokens_used,
            duration_seconds=duration,
            filled_fields=filled_fields,
            questions_answered=questions_answered,
            tier_used="T2",
            audit_trail=audit_trail,
        )
