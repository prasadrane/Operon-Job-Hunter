"""Integration tests for submitter resilience: retry, circuit breaker, graceful degradation."""

import importlib
import sys
import time
import types
from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.core.models import JobPosting, SubmissionReceipt
from src.core.resilience import CircuitBreaker, CircuitBreakerOpenError, retry
from src.core.resilience.circuit_breaker import CircuitState


# ── Stubs (reuse from test_submission_tiers pattern) ──────────────────────────

@dataclass
class TierDecision:
    tier: str
    reason: str
    fallback_chain: List[str]


@dataclass
class SessionValidationResult:
    needs_login: bool
    session_valid: bool
    reason: Optional[str] = None


class _StubRoutingEngine:
    def __init__(self, decision=None):
        self.decision = decision or TierDecision(
            tier="T1", reason="known", fallback_chain=["T2", "T3"]
        )

    def select(self, portal_type, url, page):
        return self.decision


class _StubSessionValidator:
    def __init__(self, result=None):
        self.result = result or SessionValidationResult(
            needs_login=False, session_valid=True
        )

    def validate(self, url, portal_name, page):
        return self.result


def _install_stubs():
    """Install stub modules for routing_engine and session_validator."""
    try:
        importlib.import_module("src.pipeline.4_submission.routing_engine")
    except Exception:
        re_mod = types.ModuleType("src.pipeline.4_submission.routing_engine")
        re_mod.RoutingEngine = _StubRoutingEngine
        re_mod.TierDecision = TierDecision
        sys.modules["src.pipeline.4_submission.routing_engine"] = re_mod

    try:
        importlib.import_module("src.pipeline.4_submission.session_validator")
    except Exception:
        sv_mod = types.ModuleType("src.pipeline.4_submission.session_validator")
        sv_mod.SessionValidator = _StubSessionValidator
        sv_mod.SessionValidationResult = SessionValidationResult
        sys.modules["src.pipeline.4_submission.session_validator"] = sv_mod


_install_stubs()

_se_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
SubmitterEngine = _se_mod.SubmitterEngine


def _make_job():
    return JobPosting(
        id="job-res-1",
        title="SWE",
        company="Acme",
        url="https://example.com/job/1",
        portal_type="generic",
    )


def _setup_playwright_mocks(mock_pw, mock_get_adapter):
    """Common mock setup for playwright and adapter."""
    mock_page = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_playwright = MagicMock()
    mock_playwright.__enter__ = MagicMock(return_value=mock_playwright)
    mock_playwright.__exit__ = MagicMock(return_value=False)
    mock_pw.return_value = mock_playwright

    mock_browser_ctx = MagicMock()
    mock_browser_ctx.create_context.return_value = mock_context

    mock_adapter = MagicMock()
    mock_adapter.__class__.__name__ = "GenericAdapter"
    mock_adapter.fill_form.return_value = None
    mock_adapter.submit.return_value = (False, "T1 failed")
    mock_get_adapter.return_value = mock_adapter

    return mock_browser_ctx, mock_page, mock_adapter


class TestGracefulDegradation:
    """If T2 fails, T3 is attempted (not a hard fail)."""

    def test_t2_failure_falls_through_to_t3(self):
        with patch.object(_se_mod, "sync_playwright") as mock_pw, \
             patch.object(_se_mod, "get_adapter") as mock_get_adapter:
            mock_browser_ctx, mock_page, mock_adapter = _setup_playwright_mocks(
                mock_pw, mock_get_adapter
            )

            engine = SubmitterEngine(
                browser_manager=mock_browser_ctx,
                routing_engine=_StubRoutingEngine(TierDecision(
                    tier="T1", reason="known", fallback_chain=["T2", "T3"]
                )),
                session_validator=_StubSessionValidator(),
            )

            engine._execute_t1 = MagicMock(return_value=SubmissionReceipt(
                job_id="job-res-1", success=False, portal_type="generic",
                error_message="T1 fail",
            ))
            engine._execute_t2 = MagicMock(return_value=SubmissionReceipt(
                job_id="job-res-1", success=False, portal_type="generic",
                error_message="T2 fail",
            ))
            engine._execute_t3 = MagicMock(return_value=SubmissionReceipt(
                job_id="job-res-1", success=True, portal_type="generic",
                confirmation_id="T3-CONFIRMED",
            ))

            job = _make_job()
            receipt = engine.submit(job)

            assert receipt.success is True
            assert receipt.confirmation_id == "T3-CONFIRMED"
            engine._execute_t1.assert_called_once()
            engine._execute_t2.assert_called_once()
            engine._execute_t3.assert_called_once()


class TestCircuitBreakerIntegration:
    """Circuit breaker prevents cascade failures in submitter."""

    def test_llm_circuit_open_skips_t2_and_falls_to_t3(self):
        with patch.object(_se_mod, "sync_playwright") as mock_pw, \
             patch.object(_se_mod, "get_adapter") as mock_get_adapter:
            mock_browser_ctx, mock_page, mock_adapter = _setup_playwright_mocks(
                mock_pw, mock_get_adapter
            )

            engine = SubmitterEngine(
                browser_manager=mock_browser_ctx,
                routing_engine=_StubRoutingEngine(TierDecision(
                    tier="T1", reason="known", fallback_chain=["T2", "T3"]
                )),
                session_validator=_StubSessionValidator(),
            )

            # Force LLM circuit breaker to OPEN state
            engine.llm_api_breaker._failure_count = 999
            engine.llm_api_breaker._last_failure_time = time.monotonic()
            engine.llm_api_breaker._state = CircuitState.OPEN

            engine._execute_t1 = MagicMock(return_value=SubmissionReceipt(
                job_id="job-res-1", success=False, portal_type="generic",
                error_message="T1 fail",
            ))
            engine._execute_t2 = MagicMock(
                side_effect=AssertionError("T2 should not be called when circuit is open")
            )
            engine._execute_t3 = MagicMock(return_value=SubmissionReceipt(
                job_id="job-res-1", success=True, portal_type="generic",
                confirmation_id="T3-FALLBACK",
            ))

            job = _make_job()
            receipt = engine.submit(job)

            assert receipt.success is True
            assert receipt.confirmation_id == "T3-FALLBACK"
            engine._execute_t2.assert_not_called()
            engine._execute_t3.assert_called_once()


class TestRetryIntegration:
    """Verify retry wraps tier execution in submitter."""

    def test_t1_retries_on_failure(self):
        with patch.object(_se_mod, "sync_playwright") as mock_pw, \
             patch.object(_se_mod, "get_adapter") as mock_get_adapter:
            mock_browser_ctx, mock_page, mock_adapter = _setup_playwright_mocks(
                mock_pw, mock_get_adapter
            )

            engine = SubmitterEngine(
                browser_manager=mock_browser_ctx,
                routing_engine=_StubRoutingEngine(TierDecision(
                    tier="T1", reason="known", fallback_chain=["T2", "T3"]
                )),
                session_validator=_StubSessionValidator(),
            )

            call_count = 0

            def mock_t1(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("transient browser error")
                return SubmissionReceipt(
                    job_id="job-res-1", success=True, portal_type="generic",
                    confirmation_id="T1-RETRY-OK",
                )

            engine._execute_t1 = MagicMock(side_effect=mock_t1)

            job = _make_job()
            receipt = engine.submit(job)

            assert receipt.success is True
            assert call_count == 2


class TestCircuitBreakerPreventsCascade:
    """Circuit breaker stops repeated calls to failing services."""

    def test_circuit_breaker_prevents_cascade_failures(self):
        cb = CircuitBreaker(name="test_service", failure_threshold=3,
                            recovery_timeout_sec=60)

        call_count = 0

        def flaky_service():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("service down")

        # Trip the breaker
        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.call(flaky_service)

        assert cb.state == "open"
        calls_before = call_count

        # Subsequent calls are rejected without hitting the service
        for _ in range(10):
            with pytest.raises(CircuitBreakerOpenError):
                cb.call(flaky_service)

        assert call_count == calls_before
        assert cb.metrics["total_rejected"] == 10
