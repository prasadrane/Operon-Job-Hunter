"""Submitter engine orchestrating persistent browser navigation, form filling, and receipt capture."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
import importlib
import logging
import os
import re
import uuid
from typing import Any, Callable, Dict, List, Optional, Union
from playwright.sync_api import sync_playwright

from src.core.config import get_settings
from src.core.models import CandidateProfile, JobPosting, SubmissionReceipt, TailoredArtifacts
from src.core.resilience import retry, CircuitBreaker, CircuitBreakerOpenError
from .adapters import get_adapter
from .browser_manager import BrowserManager
from .captcha_handler import CaptchaHandler
from .fastpath_engine import FastPathSubmitter
from .preflight_screener import PreflightScreener, PreflightStatus
from .qa_synthesizer import QASynthesizer


@dataclass
class SubmissionCheckpoint:
    """Snapshot of submission progress at a key stage, enabling mid-submission recovery.

    LangGraph can persist these via its checkpoint API to resume failed submissions
    without restarting from scratch.
    """
    job_id: str
    portal_type: str
    tier: str  # "T1", "T2", "T3"
    stage: str  # "preflight", "session", "captcha", "routing", "filling", "submitting"
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for PipelineGraphState storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubmissionCheckpoint":
        """Deserialize from dict (e.g. from PipelineGraphState)."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

# Digit-dir modules via importlib (SyntaxError with dotted import)
_routing_mod = importlib.import_module("src.pipeline.4_submission.routing_engine")
RoutingEngine = _routing_mod.RoutingEngine

_sv_mod = importlib.import_module("src.pipeline.4_submission.session_validator")
SessionValidator = _sv_mod.SessionValidator

_bua_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
BrowserUseSubmissionAgent = _bua_mod.BrowserUseSubmissionAgent
SubmissionTask = _bua_mod.SubmissionTask

_audit_mod = importlib.import_module("src.pipeline.4_submission.submission_audit")
log_audit = _audit_mod.log_audit

_ws_mod = importlib.import_module("src.pipeline.4_submission.websurfer_agent")
WebSurferAgent = _ws_mod.WebSurferAgent

# CredentialVault (digit-dir module). Imported lazily via helper to avoid
# hard-failing if the vault module isn't yet installed (Task 1 may be in flight).
try:
    _vault_mod = importlib.import_module("src.core.credentials.vault")
    CredentialVault = _vault_mod.CredentialVault
except Exception:  # pragma: no cover — vault may be absent in older envs
    CredentialVault = None  # type: ignore[assignment]

# Telemetry (observability metrics collection)
try:
    _telemetry_mod = importlib.import_module("src.core.telemetry.submission_telemetry")
    SubmissionTelemetry = _telemetry_mod.SubmissionTelemetry
except Exception:  # pragma: no cover — telemetry may be absent in older envs
    SubmissionTelemetry = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class SubmitterEngine:
    """End-to-end automation engine for applying to jobs across multiple ATS platforms.

    Tiered routing (T1→T2→T3):
    - T1: FastPath deterministic fill + ATS adapter submit (zero LLM cost)
    - T2: BrowserUseSubmissionAgent (LLM-driven, handles novel DOMs)
    - T3: WebSurferAgent (rule-based fallback)
    """

    def __init__(
        self,
        browser_manager: Optional[BrowserManager] = None,
        captcha_handler: Optional[CaptchaHandler] = None,
        preflight_screener: Optional[PreflightScreener] = None,
        qa_synthesizer: Optional[QASynthesizer] = None,
        fastpath_submitter: Optional[FastPathSubmitter] = None,
        routing_engine: Optional[Any] = None,
        session_validator: Optional[Any] = None,
        browser_use_agent: Optional[Any] = None,
        receipts_dir: Optional[str] = None,
        dry_run: bool = False,
        checkpoint_callback: Optional[Callable[[SubmissionCheckpoint], None]] = None,
        telemetry: Optional[Any] = None,
    ) -> None:
        self.browser_manager = browser_manager or BrowserManager()
        self.captcha_handler = captcha_handler or CaptchaHandler()
        self.preflight_screener = preflight_screener or PreflightScreener()
        self.qa_synthesizer = qa_synthesizer or QASynthesizer()
        self.fastpath_submitter = fastpath_submitter or FastPathSubmitter()
        self.routing_engine = routing_engine or RoutingEngine()
        self.session_validator = session_validator or SessionValidator()
        self.browser_use_agent = browser_use_agent or BrowserUseSubmissionAgent()
        self.receipts_dir = receipts_dir or "./output/receipts"
        self.dry_run = dry_run
        os.makedirs(self.receipts_dir, exist_ok=True)
        # WebSurferAgent instantiated lazily for T3 fallback
        self._websurfer: Optional[Any] = None
        # Checkpoint callback for mid-submission recovery (called at key stages)
        self._checkpoint_callback = checkpoint_callback
        self._checkpoints: List[SubmissionCheckpoint] = []
        # Telemetry for observability metrics
        self.telemetry = telemetry or (SubmissionTelemetry() if SubmissionTelemetry else None)
        # ── Resilience: circuit breakers for external services ───────────────
        # CapSolver: external captcha-solving service (high latency, rate-limited)
        self.capsolver_breaker = CircuitBreaker(
            name="capsolver",
            failure_threshold=5,
            recovery_timeout_sec=60,
            expected_exceptions=(Exception,),
        )
        # LLM API: used by T2 BrowserUse and other LLM-driven tiers
        self.llm_api_breaker = CircuitBreaker(
            name="llm_api",
            failure_threshold=3,
            recovery_timeout_sec=30,
            expected_exceptions=(Exception,),
        )
        # Browser automation: Playwright operations (timeout-prone)
        self.browser_breaker = CircuitBreaker(
            name="browser",
            failure_threshold=10,
            recovery_timeout_sec=45,
            expected_exceptions=(Exception,),
        )

    def _generate_screenshot_path(self, company: str, job_id: str) -> str:
        """Create timestamped path for receipt screenshot."""
        safe_company = re.sub(r"[^\w\-]", "_", company or "unknown")
        safe_job_id = re.sub(r"[^\w\-]", "_", job_id or "job")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_company}_{safe_job_id}_{timestamp}.png"
        return os.path.join(self.receipts_dir, filename)

    def _save_checkpoint(
        self,
        job_id: str,
        portal_type: str,
        tier: str,
        stage: str,
        screenshot_path: Optional[str] = None,
        error_message: Optional[str] = None,
        retry_count: int = 0,
    ) -> SubmissionCheckpoint:
        """Create a checkpoint record and invoke callback if configured.

        Checkpoints enable LangGraph mid-submission recovery: on failure,
        the pipeline can resume from the last checkpoint instead of restarting.
        """
        cp = SubmissionCheckpoint(
            job_id=job_id,
            portal_type=portal_type,
            tier=tier,
            stage=stage,
            screenshot_path=screenshot_path,
            error_message=error_message,
            retry_count=retry_count,
        )
        self._checkpoints.append(cp)
        logger.debug("Checkpoint saved: stage=%s tier=%s retry=%d", stage, tier, retry_count)
        if self._checkpoint_callback is not None:
            try:
                self._checkpoint_callback(cp)
            except Exception as cb_exc:
                logger.warning("Checkpoint callback failed: %s", cb_exc)
        return cp

    def submit(
        self,
        job: JobPosting,
        artifacts: Optional[TailoredArtifacts] = None,
        profile: Optional[Union[dict, CandidateProfile, Any]] = None,
        credential_ref: Optional[str] = None,
        resume_checkpoint: Optional[SubmissionCheckpoint] = None,
    ) -> SubmissionReceipt:
        """Execute persistent browser automation with T1→T2→T3 tiered routing.

        Flow:
          preflight → session_validate → captcha → route_select →
            T1: FastPath + adapter.fill_form + adapter.submit
              on_failure → T2: BrowserUseSubmissionAgent.submit()
                on_failure → T3: WebSurferAgent fallback
          → receipt (with tier_used in audit)

        Args:
            resume_checkpoint: If provided, resume from this checkpoint (e.g. after
                a previous failure). retry_count is incremented from the checkpoint.
        """
        logger.info("Starting submission for Job: %s at %s (%s)", job.title, job.company, job.url)
        screenshot_path: Optional[str] = None
        portal_name = job.portal_type or "generic"
        submission_id = str(uuid.uuid4())
        submission_start_time = datetime.utcnow()

        # Telemetry: record submission start
        telemetry_session_id: Optional[str] = None
        if self.telemetry:
            try:
                telemetry_session_id = self.telemetry.record_submission_start(job.id, portal_name)
            except Exception as tel_exc:
                logger.debug("Telemetry record_submission_start failed: %s", tel_exc)

        # Determine retry_count from resume checkpoint
        retry_count = 0
        if resume_checkpoint is not None:
            retry_count = resume_checkpoint.retry_count + 1
            logger.info("Resuming from checkpoint: stage=%s tier=%s retry=%d",
                        resume_checkpoint.stage, resume_checkpoint.tier, retry_count)

        # Build prof_dict once for all tiers
        prof_dict = profile if isinstance(profile, dict) else (
            profile.model_dump() if hasattr(profile, "model_dump") else (
                profile.dict() if hasattr(profile, "dict") else {}
            )
        )

        # ── Resolve credentials from vault (never stored in state) ────────────
        credentials: Optional[Dict[str, str]] = None
        if credential_ref:
            try:
                vault_cls = CredentialVault
                if vault_cls is not None:
                    vault = vault_cls()
                    entry = vault.get_credentials(credential_ref)
                    if entry is not None:
                        credentials = {
                            "username": entry.username,
                            "password": entry.password,
                            **getattr(entry, "metadata", {}),
                        }
                        logger.info("Credentials resolved from vault for ref=%s", credential_ref)
                    else:
                        logger.info("No credentials found in vault for ref=%s", credential_ref)
                else:
                    logger.debug("CredentialVault not available; continuing without credentials")
            except Exception as vault_exc:
                logger.warning("CredentialVault lookup failed for ref=%s: %s", credential_ref, vault_exc)

        with sync_playwright() as playwright:
            context = None
            page = None
            try:
                context = self.browser_manager.create_context(playwright)
                page = context.new_page()

                # Navigate to job URL
                logger.info("Navigating to %s", job.url)
                page.goto(job.url, wait_until="domcontentloaded", timeout=60000)

                # Preflight Screening (Blacklist, Knockouts, Status Screening, Prohibited Questions)
                preflight_res = self.preflight_screener.screen_page(page, company=job.company, profile=prof_dict)
                if preflight_res.status == PreflightStatus.KNOCKOUT_DISQUALIFIED:
                    logger.warning("Preflight knockout triggered for %s: %s", job.company, preflight_res.reason)
                    screenshot_path = self._generate_screenshot_path(job.company, job.id)
                    try:
                        page.screenshot(path=screenshot_path, full_page=True)
                    except Exception:
                        pass
                    return SubmissionReceipt(
                        job_id=job.id,
                        success=False,
                        portal_type=portal_name,
                        screenshot_path=screenshot_path,
                        error_message=f"Preflight Knockout: {preflight_res.reason}",
                    )
                elif preflight_res.status == PreflightStatus.BLACKLISTED:
                    logger.warning("Preflight blacklist hit for %s: %s", job.company, preflight_res.reason)
                    return SubmissionReceipt(
                        job_id=job.id,
                        success=False,
                        portal_type=portal_name,
                        error_message=f"Preflight Blacklist: {preflight_res.reason}",
                    )

                if preflight_res.has_status_screening_warning:
                    logger.warning("Preflight Notice: %s", preflight_res.status_screening_details)
                if preflight_res.has_prohibited_content_warning:
                    logger.warning("Preflight Notice: %s", preflight_res.prohibited_content_details)

                # Checkpoint: preflight passed
                self._save_checkpoint(
                    job_id=job.id,
                    portal_type=portal_name,
                    tier="",
                    stage="preflight",
                    retry_count=retry_count,
                )

                # Session Validation — must pass before attempting any tier
                try:
                    session_result = self._call_session_validate(job.url, portal_name, page)
                except Exception as sv_exc:
                    logger.warning("SessionValidator raised; treating as needs_login=False: %s", sv_exc)
                    session_result = None

                if session_result is not None and getattr(session_result, "needs_login", False):
                    sv_reason = getattr(session_result, "error", None) or getattr(session_result, "reason", "session_invalid")
                    logger.warning("Session validation failed for %s: %s", job.url, sv_reason)
                    try:
                        log_audit(
                            submission_id=submission_id,
                            action_type="session_validate",
                            target=job.url,
                            success=False,
                            job_id=job.id,
                            company=job.company,
                            portal_type=portal_name,
                            tier=None,
                            error_detail=sv_reason,
                        )
                    except Exception:
                        pass
                    return SubmissionReceipt(
                        job_id=job.id,
                        success=False,
                        portal_type=portal_name,
                        error_message=f"Session expired: needs re-login ({sv_reason})",
                    )

                try:
                    log_audit(
                        submission_id=submission_id,
                        action_type="session_validate",
                        target=job.url,
                        success=True,
                        job_id=job.id,
                        company=job.company,
                        portal_type=portal_name,
                        tier=None,
                    )
                except Exception:
                    pass

                # Checkpoint: session validated
                self._save_checkpoint(
                    job_id=job.id,
                    portal_type=portal_name,
                    tier="",
                    stage="session",
                    retry_count=retry_count,
                )

                # CAPTCHA & Bot challenge inspection
                if self.captcha_handler.detect_captcha(page):
                    logger.warning("CAPTCHA detected on %s. Triggering human solve handler...", job.url)
                    solved = self.captcha_handler.wait_for_human_solve(page)
                    if not solved:
                        screenshot_path = self._generate_screenshot_path(job.company, job.id)
                        try:
                            page.screenshot(path=screenshot_path, full_page=True)
                        except Exception:
                            pass
                        return SubmissionReceipt(
                            job_id=job.id,
                            success=False,
                            portal_type=portal_name,
                            screenshot_path=screenshot_path,
                            error_message="CAPTCHA challenge was not solved within timeout period.",
                        )

                # Checkpoint: captcha cleared (no CAPTCHA or solved)
                self._save_checkpoint(
                    job_id=job.id,
                    portal_type=portal_name,
                    tier="",
                    stage="captcha",
                    retry_count=retry_count,
                )

                # Select specialized ATS adapter (also determines portal_name for T1)
                adapter = get_adapter(job.url, page)
                portal_name = adapter.__class__.__name__
                logger.info("Selected ATS adapter: %s", portal_name)

                # ---- Tier routing ----
                # Route on the job's declared portal_type (semantic) — falls back
                # to adapter class name if job didn't specify one.
                route_portal_type = job.portal_type or portal_name
                try:
                    decision = self.routing_engine.select(
                        portal_type=route_portal_type, url=job.url, page=page,
                    )
                except Exception as route_exc:
                    logger.warning("RoutingEngine.select failed; defaulting to T1: %s", route_exc)
                    decision = None

                # Default decision if routing engine missing or failed
                if decision is None:
                    class _DefaultDecision:
                        tier = "T1"
                        reason = "default"
                        fallback_chain = ["T2", "T3"]
                    decision = _DefaultDecision()

                logger.info("Routing decision: tier=%s reason=%s fallback=%s",
                            decision.tier, decision.reason, decision.fallback_chain)

                try:
                    log_audit(
                        submission_id=submission_id,
                        action_type="route_select",
                        target=job.url,
                        success=True,
                        job_id=job.id,
                        company=job.company,
                        portal_type=portal_name,
                        tier=decision.tier,
                        metadata={"reason": decision.reason, "fallback": list(decision.fallback_chain)},
                    )
                except Exception:
                    pass

                # Checkpoint: routing decision made
                self._save_checkpoint(
                    job_id=job.id,
                    portal_type=portal_name,
                    tier=decision.tier,
                    stage="routing",
                    retry_count=retry_count,
                )

                # ---- T1: FastPath + adapter ----
                t1_receipt: Optional[SubmissionReceipt] = None
                if decision.tier == "T1":
                    # Telemetry: T1 attempt start
                    t1_started = datetime.utcnow().isoformat()
                    if self.telemetry and telemetry_session_id:
                        try:
                            self.telemetry.record_tier_attempt(telemetry_session_id, "T1", t1_started)
                        except Exception:
                            pass

                    # Wrap T1 execution with retry + browser circuit breaker
                    @retry(max_attempts=2, delay_sec=0.5, backoff_factor=2.0,
                           exceptions=(Exception,))
                    def _t1_with_retry():
                        return self.browser_breaker.call(
                            self._execute_t1,
                            page, job, artifacts, prof_dict, adapter, portal_name,
                            submission_id, credentials=credentials,
                        )
                    t1_receipt = _t1_with_retry()

                    # Telemetry: T1 attempt result
                    if self.telemetry and telemetry_session_id:
                        try:
                            t1_duration = (datetime.utcnow() - datetime.fromisoformat(t1_started)).total_seconds()
                            self.telemetry.record_tier_result(
                                telemetry_session_id, "T1",
                                success=t1_receipt.success if t1_receipt else False,
                                duration_sec=t1_duration,
                                tokens_used=0,  # T1 is deterministic, no LLM tokens
                                error_type=t1_receipt.error_message if t1_receipt and not t1_receipt.success else None,
                            )
                        except Exception:
                            pass

                    # Checkpoint: T1 attempt completed
                    self._save_checkpoint(
                        job_id=job.id,
                        portal_type=portal_name,
                        tier="T1",
                        stage="filling",
                        screenshot_path=getattr(t1_receipt, "screenshot_path", None),
                        error_message=t1_receipt.error_message if not t1_receipt.success else None,
                        retry_count=retry_count,
                    )
                    # Checkpoint: submitting (final stage before return)
                    self._save_checkpoint(
                        job_id=job.id,
                        portal_type=portal_name,
                        tier="T1",
                        stage="submitting",
                        screenshot_path=getattr(t1_receipt, "screenshot_path", None),
                        error_message=t1_receipt.error_message if not t1_receipt.success else None,
                        retry_count=retry_count,
                    )
                    # Dry-run short-circuit (existing behaviour preserved)
                    if self.dry_run and t1_receipt is not None:
                        # Telemetry: submission end (dry-run)
                        if self.telemetry and telemetry_session_id:
                            try:
                                total_duration = (datetime.utcnow() - submission_start_time).total_seconds()
                                self.telemetry.record_submission_end(
                                    telemetry_session_id,
                                    success=True,
                                    total_duration_sec=total_duration,
                                    tiers_attempted=["T1"],
                                    final_tier="T1",
                                )
                            except Exception:
                                pass
                        return t1_receipt
                    if t1_receipt is not None and t1_receipt.success:
                        # Telemetry: submission end (T1 success)
                        if self.telemetry and telemetry_session_id:
                            try:
                                total_duration = (datetime.utcnow() - submission_start_time).total_seconds()
                                self.telemetry.record_submission_end(
                                    telemetry_session_id,
                                    success=True,
                                    total_duration_sec=total_duration,
                                    tiers_attempted=["T1"],
                                    final_tier="T1",
                                )
                            except Exception:
                                pass
                        return t1_receipt
                    # T1 failed and T2 is in fallback chain
                    if t1_receipt is not None and not t1_receipt.success:
                        if "T2" not in decision.fallback_chain:
                            # Telemetry: submission end (T1 failed, no T2 fallback)
                            if self.telemetry and telemetry_session_id:
                                try:
                                    total_duration = (datetime.utcnow() - submission_start_time).total_seconds()
                                    self.telemetry.record_submission_end(
                                        telemetry_session_id,
                                        success=False,
                                        total_duration_sec=total_duration,
                                        tiers_attempted=["T1"],
                                        final_tier="T1",
                                    )
                                except Exception:
                                    pass
                            return t1_receipt
                        logger.warning("T1 failed (%s); escalating to T2",
                                       t1_receipt.error_message)
                        try:
                            log_audit(
                                submission_id=submission_id,
                                action_type="tier_escalate",
                                target="T2",
                                success=True,
                                job_id=job.id,
                                company=job.company,
                                portal_type=portal_name,
                                tier="T2",
                                metadata={"from_tier": "T1"},
                            )
                        except Exception:
                            pass

                # ---- T2: BrowserUse ----
                t2_receipt: Optional[SubmissionReceipt] = None
                if decision.tier == "T2" or (t1_receipt is not None and not t1_receipt.success
                                             and "T2" in decision.fallback_chain):
                    # Telemetry: T2 attempt start
                    t2_started = datetime.utcnow().isoformat()
                    if self.telemetry and telemetry_session_id:
                        try:
                            self.telemetry.record_tier_attempt(telemetry_session_id, "T2", t2_started)
                        except Exception:
                            pass

                    # Wrap T2 execution with retry + LLM API circuit breaker
                    @retry(max_attempts=2, delay_sec=1.0, backoff_factor=2.0,
                           exceptions=(Exception,))
                    def _t2_with_retry():
                        return self.llm_api_breaker.call(
                            self._execute_t2,
                            job, artifacts, prof_dict, portal_name, submission_id,
                            credentials=credentials,
                        )

                    if not self.llm_api_breaker.allow_request():
                        logger.warning(
                            "LLM API circuit OPEN; skipping T2 and falling through to T3"
                        )
                        t2_receipt = SubmissionReceipt(
                            job_id=job.id, success=False, portal_type=portal_name,
                            error_message="T2 skipped: LLM API circuit open",
                        )
                    else:
                        try:
                            t2_receipt = _t2_with_retry()
                        except CircuitBreakerOpenError as cb_exc:
                            logger.warning("T2 circuit breaker opened: %s", cb_exc)
                            t2_receipt = SubmissionReceipt(
                                job_id=job.id, success=False, portal_type=portal_name,
                                error_message=f"T2 circuit breaker open: {cb_exc}",
                            )
                        except Exception as t2_exc:
                            logger.warning("T2 failed after retries: %s", t2_exc)
                            t2_receipt = SubmissionReceipt(
                                job_id=job.id, success=False, portal_type=portal_name,
                                error_message=f"T2 exhausted: {t2_exc}",
                            )

                    # Telemetry: T2 attempt result
                    if self.telemetry and telemetry_session_id:
                        try:
                            t2_duration = (datetime.utcnow() - datetime.fromisoformat(t2_started)).total_seconds()
                            self.telemetry.record_tier_result(
                                telemetry_session_id, "T2",
                                success=t2_receipt.success if t2_receipt else False,
                                duration_sec=t2_duration,
                                tokens_used=getattr(t2_receipt, 'tokens_used', 0) if t2_receipt else 0,
                                error_type=t2_receipt.error_message if t2_receipt and not t2_receipt.success else None,
                            )
                        except Exception:
                            pass
                    # Checkpoint: T2 attempt completed
                    self._save_checkpoint(
                        job_id=job.id,
                        portal_type=portal_name,
                        tier="T2",
                        stage="filling",
                        screenshot_path=getattr(t2_receipt, "screenshot_path", None),
                        error_message=t2_receipt.error_message if not t2_receipt.success else None,
                        retry_count=retry_count,
                    )
                    self._save_checkpoint(
                        job_id=job.id,
                        portal_type=portal_name,
                        tier="T2",
                        stage="submitting",
                        screenshot_path=getattr(t2_receipt, "screenshot_path", None),
                        error_message=t2_receipt.error_message if not t2_receipt.success else None,
                        retry_count=retry_count,
                    )
                    if t2_receipt.success:
                        # Telemetry: submission end (T2 success)
                        if self.telemetry and telemetry_session_id:
                            try:
                                total_duration = (datetime.utcnow() - submission_start_time).total_seconds()
                                self.telemetry.record_submission_end(
                                    telemetry_session_id,
                                    success=True,
                                    total_duration_sec=total_duration,
                                    tiers_attempted=["T1", "T2"] if t1_receipt else ["T2"],
                                    final_tier="T2",
                                )
                            except Exception:
                                pass
                        return t2_receipt
                    if "T3" not in decision.fallback_chain:
                        # Telemetry: submission end (T2 failed, no T3 fallback)
                        if self.telemetry and telemetry_session_id:
                            try:
                                total_duration = (datetime.utcnow() - submission_start_time).total_seconds()
                                self.telemetry.record_submission_end(
                                    telemetry_session_id,
                                    success=False,
                                    total_duration_sec=total_duration,
                                    tiers_attempted=["T1", "T2"] if t1_receipt else ["T2"],
                                    final_tier="T2",
                                )
                            except Exception:
                                pass
                        return t2_receipt
                    logger.warning("T2 failed (%s); escalating to T3", t2_receipt.error_message)
                    try:
                        log_audit(
                            submission_id=submission_id,
                            action_type="tier_escalate",
                            target="T3",
                            success=True,
                            job_id=job.id,
                            company=job.company,
                            portal_type=portal_name,
                            tier="T3",
                            metadata={"from_tier": "T2"},
                        )
                    except Exception:
                        pass

                # ---- T3: WebSurfer ----
                if decision.tier == "T3" or (t2_receipt is not None and not t2_receipt.success
                                             and "T3" in decision.fallback_chain):
                    # Telemetry: T3 attempt start
                    t3_started = datetime.utcnow().isoformat()
                    if self.telemetry and telemetry_session_id:
                        try:
                            self.telemetry.record_tier_attempt(telemetry_session_id, "T3", t3_started)
                        except Exception:
                            pass

                    # Wrap T3 execution with retry + browser circuit breaker
                    @retry(max_attempts=2, delay_sec=0.5, backoff_factor=2.0,
                           exceptions=(Exception,))
                    def _t3_with_retry():
                        return self.browser_breaker.call(
                            self._execute_t3,
                            page, job, prof_dict, portal_name, submission_id,
                            credentials=credentials,
                        )

                    if not self.browser_breaker.allow_request():
                        logger.warning("Browser circuit OPEN; T3 may fail")
                    try:
                        t3_receipt = _t3_with_retry()
                    except CircuitBreakerOpenError as cb_exc:
                        logger.warning("T3 circuit breaker opened: %s", cb_exc)
                        t3_receipt = SubmissionReceipt(
                            job_id=job.id, success=False, portal_type=portal_name,
                            error_message=f"T3 circuit breaker open: {cb_exc}",
                        )
                    except Exception as t3_exc:
                        logger.warning("T3 failed after retries: %s", t3_exc)
                        t3_receipt = SubmissionReceipt(
                            job_id=job.id, success=False, portal_type=portal_name,
                            error_message=f"T3 exhausted: {t3_exc}",
                        )

                    # Telemetry: T3 attempt result
                    if self.telemetry and telemetry_session_id:
                        try:
                            t3_duration = (datetime.utcnow() - datetime.fromisoformat(t3_started)).total_seconds()
                            self.telemetry.record_tier_result(
                                telemetry_session_id, "T3",
                                success=t3_receipt.success if t3_receipt else False,
                                duration_sec=t3_duration,
                                tokens_used=0,  # T3 is rule-based, no LLM tokens
                                error_type=t3_receipt.error_message if t3_receipt and not t3_receipt.success else None,
                            )
                        except Exception:
                            pass
                    # Checkpoint: T3 attempt completed
                    self._save_checkpoint(
                        job_id=job.id,
                        portal_type=portal_name,
                        tier="T3",
                        stage="filling",
                        screenshot_path=getattr(t3_receipt, "screenshot_path", None),
                        error_message=t3_receipt.error_message if not t3_receipt.success else None,
                        retry_count=retry_count,
                    )
                    self._save_checkpoint(
                        job_id=job.id,
                        portal_type=portal_name,
                        tier="T3",
                        stage="submitting",
                        screenshot_path=getattr(t3_receipt, "screenshot_path", None),
                        error_message=t3_receipt.error_message if not t3_receipt.success else None,
                        retry_count=retry_count,
                    )
                    # Telemetry: submission end (T3 final)
                    if self.telemetry and telemetry_session_id:
                        try:
                            total_duration = (datetime.utcnow() - submission_start_time).total_seconds()
                            self.telemetry.record_submission_end(
                                telemetry_session_id,
                                success=t3_receipt.success if t3_receipt else False,
                                total_duration_sec=total_duration,
                                tiers_attempted=["T1", "T2", "T3"] if t1_receipt and t2_receipt else ["T2", "T3"] if t2_receipt else ["T3"],
                                final_tier="T3",
                            )
                        except Exception:
                            pass
                    return t3_receipt

                # No tier matched or all fallbacks exhausted without explicit T3
                # Telemetry: submission end (all tiers exhausted)
                if self.telemetry and telemetry_session_id:
                    try:
                        total_duration = (datetime.utcnow() - submission_start_time).total_seconds()
                        self.telemetry.record_submission_end(
                            telemetry_session_id,
                            success=False,
                            total_duration_sec=total_duration,
                            tiers_attempted=["T1", "T2", "T3"],
                            final_tier=None,
                        )
                    except Exception:
                        pass
                return SubmissionReceipt(
                    job_id=job.id,
                    success=False,
                    portal_type=portal_name,
                    error_message="All submission tiers exhausted without success.",
                )

            except Exception as exc:
                logger.exception("Error during job submission for %s: %s", job.id, exc)
                try:
                    from src.core.db.error_log import log_error
                    log_error(
                        source="submission",
                        component="submitter_engine",
                        error_type="SUBMISSION_ERROR",
                        message=f"Error during job submission for {job.id}: {exc}",
                        company=getattr(job, "company", None),
                        metadata={"job_id": getattr(job, "id", None), "url": getattr(job, "url", None)},
                    )
                except Exception:
                    pass
                if page:
                    try:
                        if not screenshot_path:
                            screenshot_path = self._generate_screenshot_path(job.company, job.id)
                        page.screenshot(path=screenshot_path, full_page=True)
                    except Exception:
                        pass
                # Telemetry: submission end (exception)
                if self.telemetry and telemetry_session_id:
                    try:
                        total_duration = (datetime.utcnow() - submission_start_time).total_seconds()
                        self.telemetry.record_submission_end(
                            telemetry_session_id,
                            success=False,
                            total_duration_sec=total_duration,
                            tiers_attempted=[],  # Unknown which tiers were attempted
                            final_tier=None,
                        )
                    except Exception:
                        pass
                return SubmissionReceipt(
                    job_id=job.id,
                    success=False,
                    screenshot_path=screenshot_path,
                    portal_type=portal_name,
                    error_message=str(exc),
                )
            finally:
                if context:
                    try:
                        context.close()
                    except Exception:
                        pass

    # ---- Helpers ----

    def _call_session_validate(self, url: str, portal_name: str, page):
        """Bridge sync submit() → SessionValidator.validate().

        If validate_sync() is available (real SessionValidator on sync Playwright page),
        call it directly on the current thread to avoid greenlet thread-switch errors.
        If validate() is sync (stubs/tests), call directly. If async, bridge via asyncio.
        """
        if type(self.session_validator).__name__ == "SessionValidator":
            return self.session_validator.validate_sync(url, portal_name, page)

        import asyncio

        try:
            result = self.session_validator.validate(url, portal_name, page)
        except TypeError:
            # Method may be async; bridge via asyncio
            result = self.session_validator.validate(url, portal_name, page)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        return pool.submit(asyncio.run, result).result()
                else:
                    return asyncio.run(result)
            return result
        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, result).result()
            return asyncio.run(result)
        return result

    # ---- Tier execution helpers ----

    def _execute_t1(
        self, page, job, artifacts, prof_dict, adapter, portal_name, submission_id,
        credentials: Optional[Dict[str, str]] = None,
    ) -> SubmissionReceipt:
        """T1: FastPath deterministic fill + ATS adapter submit."""
        logger.info("FastPath: filling standard profile fields...")
        resume_path = None
        if artifacts and hasattr(artifacts, "resume_pdf_path") and artifacts.resume_pdf_path:
            resume_path = str(artifacts.resume_pdf_path)
        try:
            self.fastpath_submitter.fill_profile(
                page, prof_dict, resume_path=resume_path, company=job.company,
            )
        except Exception as fp_exc:
            logger.warning("FastPath fill failed, adapter will handle: %s", fp_exc)

        logger.info("Filling ATS-specific form fields via %s...", portal_name)
        adapter.fill_form(page, job, artifacts, profile=None)

        screenshot_path = self._generate_screenshot_path(job.company, job.id)

        if self.dry_run:
            logger.info("Dry run mode active: Skipping final submit click.")
            try:
                page.screenshot(path=screenshot_path, full_page=True)
            except Exception as e:
                logger.warning("Failed to capture dry-run screenshot: %s", e)
            return SubmissionReceipt(
                job_id=job.id,
                success=True,
                confirmation_id="DRY_RUN_CONFIRMED",
                screenshot_path=screenshot_path,
                portal_type=portal_name,
            )

        logger.info("Triggering final submission click (T1)...")
        success, confirmation_id = adapter.submit(page)

        try:
            page.screenshot(path=screenshot_path, full_page=True)
        except Exception as e:
            logger.warning("Failed to capture post-submit screenshot: %s", e)

        return SubmissionReceipt(
            job_id=job.id,
            success=success,
            confirmation_id=confirmation_id if success else None,
            screenshot_path=screenshot_path,
            portal_type=portal_name,
            error_message=None if success else f"Submission verification failed: {confirmation_id}",
        )

    def _execute_t2(
        self, job, artifacts, prof_dict, portal_name, submission_id,
        credentials: Optional[Dict[str, str]] = None,
    ) -> SubmissionReceipt:
        """T2: BrowserUseSubmissionAgent (async → sync bridge)."""
        logger.info("Executing T2: BrowserUseSubmissionAgent for %s", job.url)
        import asyncio

        resume_path = None
        cover_letter_path = None
        if artifacts:
            if getattr(artifacts, "resume_pdf_path", None):
                resume_path = str(artifacts.resume_pdf_path)
            if getattr(artifacts, "cover_letter_path", None):
                cover_letter_path = str(artifacts.cover_letter_path)

        task = SubmissionTask(
            job_url=job.url,
            company=job.company,
            title=job.title,
            portal_type=portal_name,
            job_id=job.id,
            profile=prof_dict,
            resume_pdf_path=resume_path,
            cover_letter_path=cover_letter_path,
            credentials=credentials,
            job_description=getattr(job, "description", None),
            star_narratives=None,
        )

        try:
            # Bridge async submit → sync return
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    bu_result = pool.submit(asyncio.run, self.browser_use_agent.submit(task)).result()
            else:
                bu_result = asyncio.run(self.browser_use_agent.submit(task))
        except Exception as bu_exc:
            logger.exception("T2 BrowserUse raised: %s", bu_exc)
            try:
                log_audit(
                    submission_id=submission_id,
                    action_type="submit",
                    target=job.url,
                    success=False,
                    job_id=job.id,
                    company=job.company,
                    portal_type=portal_name,
                    tier="T2",
                    error_detail=str(bu_exc),
                )
            except Exception:
                pass
            return SubmissionReceipt(
                job_id=job.id,
                success=False,
                portal_type=portal_name,
                error_message=f"T2 BrowserUse error: {bu_exc}",
            )

        screenshot_path = self._generate_screenshot_path(job.company, job.id)
        return SubmissionReceipt(
            job_id=job.id,
            success=bool(getattr(bu_result, "success", False)),
            confirmation_id=getattr(bu_result, "confirmation_id", None) if getattr(bu_result, "success", False) else None,
            screenshot_path=screenshot_path,
            portal_type=portal_name,
            error_message=None if getattr(bu_result, "success", False) else getattr(bu_result, "error_message", "T2 failed"),
        )

    def _execute_t3(
        self, page, job, prof_dict, portal_name, submission_id,
        credentials: Optional[Dict[str, str]] = None,
    ) -> SubmissionReceipt:
        """T3: WebSurferAgent rule-based fallback."""
        logger.info("Executing T3: WebSurferAgent for %s", job.url)
        try:
            if self._websurfer is None:
                self._websurfer = WebSurferAgent()
            ws_result = self._websurfer.run(
                page=page,
                job_url=job.url,
                company=job.company,
                profile=prof_dict,
            ) if hasattr(self._websurfer, "run") else {}
        except Exception as ws_exc:
            logger.exception("T3 WebSurfer raised: %s", ws_exc)
            try:
                log_audit(
                    submission_id=submission_id,
                    action_type="submit",
                    target=job.url,
                    success=False,
                    job_id=job.id,
                    company=job.company,
                    portal_type=portal_name,
                    tier="T3",
                    error_detail=str(ws_exc),
                )
            except Exception:
                pass
            return SubmissionReceipt(
                job_id=job.id,
                success=False,
                portal_type=portal_name,
                error_message=f"T3 WebSurfer error: {ws_exc}",
            )

        screenshot_path = self._generate_screenshot_path(job.company, job.id)
        if isinstance(ws_result, dict):
            success = bool(ws_result.get("success", False))
            confirmation_id = ws_result.get("confirmation_id") if success else None
            error_msg = ws_result.get("error") if not success else None
        else:
            success = False
            confirmation_id = None
            error_msg = "T3 WebSurfer returned unexpected result"

        return SubmissionReceipt(
            job_id=job.id,
            success=success,
            confirmation_id=confirmation_id,
            screenshot_path=screenshot_path,
            portal_type=portal_name,
            error_message=error_msg or ("All submission tiers exhausted without success." if not success else None),
        )
