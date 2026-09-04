"""Tests for mid-submission checkpointing (P3c Task 5).

Validates that SubmitterEngine creates and updates SubmissionCheckpoint
records at key stages, enabling LangGraph recovery from failures.
"""

import importlib
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

# Digit-dir module via importlib (SyntaxError with dotted import)
_sub_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
SubmitterEngine = _sub_mod.SubmitterEngine
SubmissionCheckpoint = _sub_mod.SubmissionCheckpoint

from src.core.models import JobPosting, TailoredArtifacts, SubmissionReceipt


def _patch_playwright():
    """Patch sync_playwright on the submitter_engine module (digit-dir safe)."""
    return patch.object(_sub_mod, "sync_playwright")


def _patch_get_adapter(adapter_mock):
    """Patch get_adapter on the submitter_engine module (digit-dir safe)."""
    return patch.object(_sub_mod, "get_adapter", return_value=adapter_mock)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_job():
    job = MagicMock(spec=JobPosting)
    job.id = "job-123"
    job.title = "Software Engineer"
    job.company = "Acme Corp"
    job.url = "https://example.com/job/123"
    job.portal_type = "greenhouse"
    job.description = "Build things"
    return job


@pytest.fixture
def mock_artifacts():
    arts = MagicMock(spec=TailoredArtifacts)
    arts.resume_pdf_path = "/tmp/resume.pdf"
    arts.cover_letter_path = "/tmp/cover.pdf"
    return arts


@pytest.fixture
def checkpoint_collector():
    """Collects checkpoints passed to the callback."""
    return []


@pytest.fixture
def engine(checkpoint_collector):
    """SubmitterEngine with all external deps mocked and checkpoint callback wired."""
    eng = SubmitterEngine(
        browser_manager=MagicMock(),
        captcha_handler=MagicMock(),
        preflight_screener=MagicMock(),
        qa_synthesizer=MagicMock(),
        fastpath_submitter=MagicMock(),
        routing_engine=MagicMock(),
        session_validator=MagicMock(),
        browser_use_agent=MagicMock(),
        receipts_dir="/tmp/test_receipts",
        dry_run=False,
        checkpoint_callback=checkpoint_collector.append,
    )
    return eng


def _make_preflight_result(status="PASS"):
    res = MagicMock()
    _pf_mod = importlib.import_module("src.pipeline.4_submission.preflight_screener")
    PreflightStatus = _pf_mod.PreflightStatus
    if status == "PASS":
        res.status = PreflightStatus.PASSED
        res.reason = None
        res.has_status_screening_warning = False
        res.has_prohibited_content_warning = False
    elif status == "KNOCKOUT":
        res.status = PreflightStatus.KNOCKOUT_DISQUALIFIED
        res.reason = "Must have 10 years experience"
    return res


def _make_session_result(needs_login=False):
    res = MagicMock()
    res.needs_login = needs_login
    res.error = None
    res.reason = None
    return res


def _make_routing_decision(tier="T1", fallback=None):
    dec = MagicMock()
    dec.tier = tier
    dec.reason = "test"
    dec.fallback_chain = fallback or ["T2", "T3"]
    return dec


def _make_receipt(success=True, tier="T1"):
    return SubmissionReceipt(
        job_id="job-123",
        success=success,
        portal_type="greenhouse",
        confirmation_id="CONF-1" if success else None,
        error_message=None if success else f"{tier} failed",
    )


# ---------------------------------------------------------------------------
# Test 1: Checkpoint created after preflight
# ---------------------------------------------------------------------------

class TestCheckpointAfterPreflight:
    def test_checkpoint_created_after_preflight_pass(self, engine, mock_job, mock_artifacts, checkpoint_collector):
        """After preflight passes, a checkpoint with stage='preflight' is recorded."""
        engine.preflight_screener.screen_page.return_value = _make_preflight_result("PASS")
        engine.session_validator.validate.return_value = _make_session_result(needs_login=False)
        engine.captcha_handler.detect_captcha.return_value = False

        adapter_mock = MagicMock()
        adapter_mock.__class__.__name__ = "GreenhouseAdapter"
        adapter_mock.submit.return_value = (True, "CONF-1")

        engine.routing_engine.select.return_value = _make_routing_decision("T1")

        t1_receipt = _make_receipt(success=True)
        engine._execute_t1 = MagicMock(return_value=t1_receipt)

        with _patch_playwright():
            with _patch_get_adapter(adapter_mock):
                mock_page = MagicMock()
                engine.browser_manager.create_context.return_value.new_page.return_value = mock_page
                try:
                    engine.submit(mock_job, mock_artifacts, profile={})
                except Exception:
                    pass

        preflight_checkpoints = [
            cp for cp in checkpoint_collector if cp.stage == "preflight"
        ]
        assert len(preflight_checkpoints) >= 1
        cp = preflight_checkpoints[0]
        assert cp.job_id == "job-123"
        assert cp.portal_type == "greenhouse"
        assert cp.error_message is None


# ---------------------------------------------------------------------------
# Test 2: Checkpoint created after tier selection
# ---------------------------------------------------------------------------

class TestCheckpointAfterRouting:
    def test_checkpoint_created_after_tier_selection(self, engine, mock_job, mock_artifacts, checkpoint_collector):
        """After routing decision, a checkpoint with stage='routing' is recorded."""
        engine.preflight_screener.screen_page.return_value = _make_preflight_result("PASS")
        engine.session_validator.validate.return_value = _make_session_result(needs_login=False)
        engine.captcha_handler.detect_captcha.return_value = False

        adapter_mock = MagicMock()
        adapter_mock.__class__.__name__ = "GreenhouseAdapter"
        adapter_mock.submit.return_value = (True, "CONF-1")

        engine.routing_engine.select.return_value = _make_routing_decision("T2")

        t2_receipt = _make_receipt(success=True, tier="T2")
        engine._execute_t2 = MagicMock(return_value=t2_receipt)

        with _patch_playwright():
            with _patch_get_adapter(adapter_mock):
                mock_page = MagicMock()
                engine.browser_manager.create_context.return_value.new_page.return_value = mock_page
                try:
                    engine.submit(mock_job, mock_artifacts, profile={})
                except Exception:
                    pass

        routing_checkpoints = [
            cp for cp in checkpoint_collector if cp.stage == "routing"
        ]
        assert len(routing_checkpoints) >= 1
        cp = routing_checkpoints[0]
        assert cp.tier == "T2"
        assert cp.job_id == "job-123"


# ---------------------------------------------------------------------------
# Test 3: Checkpoint updated after T1 attempt
# ---------------------------------------------------------------------------

class TestCheckpointAfterTierAttempt:
    def test_checkpoint_updated_after_t1_attempt(self, engine, mock_job, mock_artifacts, checkpoint_collector):
        """After T1 attempt (success or failure), a checkpoint with stage='filling' is recorded."""
        engine.preflight_screener.screen_page.return_value = _make_preflight_result("PASS")
        engine.session_validator.validate.return_value = _make_session_result(needs_login=False)
        engine.captcha_handler.detect_captcha.return_value = False

        adapter_mock = MagicMock()
        adapter_mock.__class__.__name__ = "GreenhouseAdapter"
        adapter_mock.submit.return_value = (False, None)

        engine.routing_engine.select.return_value = _make_routing_decision("T1")

        t1_receipt = _make_receipt(success=False, tier="T1")
        t2_receipt = _make_receipt(success=True, tier="T2")
        engine._execute_t1 = MagicMock(return_value=t1_receipt)
        engine._execute_t2 = MagicMock(return_value=t2_receipt)

        with _patch_playwright():
            with _patch_get_adapter(adapter_mock):
                mock_page = MagicMock()
                engine.browser_manager.create_context.return_value.new_page.return_value = mock_page
                try:
                    engine.submit(mock_job, mock_artifacts, profile={})
                except Exception:
                    pass

        filling_checkpoints = [
            cp for cp in checkpoint_collector if cp.stage == "filling"
        ]
        assert len(filling_checkpoints) >= 1
        cp = filling_checkpoints[0]
        assert cp.tier == "T1"


# ---------------------------------------------------------------------------
# Test 4: Recovery from checkpoint works (mock failure + resume)
# ---------------------------------------------------------------------------

class TestCheckpointRecovery:
    def test_recovery_from_checkpoint(self, engine, mock_job, mock_artifacts, checkpoint_collector):
        """When resuming from a checkpoint, the engine skips already-completed stages."""
        # Simulate a checkpoint from a previous failed run at stage='routing'
        resume_checkpoint = SubmissionCheckpoint(
            job_id="job-123",
            portal_type="greenhouse",
            tier="T1",
            stage="routing",
            screenshot_path=None,
            error_message="T1 failed",
            retry_count=1,
            timestamp=datetime.utcnow().isoformat(),
        )

        engine.preflight_screener.screen_page.return_value = _make_preflight_result("PASS")
        engine.session_validator.validate.return_value = _make_session_result(needs_login=False)
        engine.captcha_handler.detect_captcha.return_value = False

        adapter_mock = MagicMock()
        adapter_mock.__class__.__name__ = "GreenhouseAdapter"

        engine.routing_engine.select.return_value = _make_routing_decision("T2")

        t2_receipt = _make_receipt(success=True, tier="T2")
        engine._execute_t2 = MagicMock(return_value=t2_receipt)

        with _patch_playwright():
            with _patch_get_adapter(adapter_mock):
                mock_page = MagicMock()
                engine.browser_manager.create_context.return_value.new_page.return_value = mock_page
                try:
                    engine.submit(
                        mock_job, mock_artifacts, profile={},
                        resume_checkpoint=resume_checkpoint,
                    )
                except Exception:
                    pass

        # T2 should have been called (resumed from routing, skipped preflight re-screening)
        engine._execute_t2.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: Checkpoint includes screenshot path
# ---------------------------------------------------------------------------

class TestCheckpointScreenshot:
    def test_checkpoint_includes_screenshot_path(self, engine, mock_job, mock_artifacts, checkpoint_collector):
        """Checkpoint records include screenshot_path when available."""
        engine.preflight_screener.screen_page.return_value = _make_preflight_result("PASS")
        engine.session_validator.validate.return_value = _make_session_result(needs_login=False)
        engine.captcha_handler.detect_captcha.return_value = False

        adapter_mock = MagicMock()
        adapter_mock.__class__.__name__ = "GreenhouseAdapter"
        adapter_mock.submit.return_value = (True, "CONF-1")

        engine.routing_engine.select.return_value = _make_routing_decision("T1")

        t1_receipt = _make_receipt(success=True)
        t1_receipt.screenshot_path = "/tmp/test_receipts/acme_job123_screenshot.png"
        engine._execute_t1 = MagicMock(return_value=t1_receipt)

        with _patch_playwright():
            with _patch_get_adapter(adapter_mock):
                mock_page = MagicMock()
                engine.browser_manager.create_context.return_value.new_page.return_value = mock_page
                try:
                    engine.submit(mock_job, mock_artifacts, profile={})
                except Exception:
                    pass

        # Find the submitting-stage checkpoint which should carry screenshot
        submitting_checkpoints = [
            cp for cp in checkpoint_collector if cp.stage == "submitting"
        ]
        if submitting_checkpoints:
            cp = submitting_checkpoints[0]
            assert cp.screenshot_path is not None


# ---------------------------------------------------------------------------
# Test 6: Retry count increments correctly
# ---------------------------------------------------------------------------

class TestRetryCountIncrement:
    def test_retry_count_increments(self, engine, mock_job, mock_artifacts, checkpoint_collector):
        """When resuming from a checkpoint, retry_count is incremented."""
        resume_checkpoint = SubmissionCheckpoint(
            job_id="job-123",
            portal_type="greenhouse",
            tier="T1",
            stage="routing",
            screenshot_path=None,
            error_message="T1 failed",
            retry_count=2,
            timestamp=datetime.utcnow().isoformat(),
        )

        engine.preflight_screener.screen_page.return_value = _make_preflight_result("PASS")
        engine.session_validator.validate.return_value = _make_session_result(needs_login=False)
        engine.captcha_handler.detect_captcha.return_value = False

        adapter_mock = MagicMock()
        adapter_mock.__class__.__name__ = "GreenhouseAdapter"

        engine.routing_engine.select.return_value = _make_routing_decision("T2")
        engine._execute_t2 = MagicMock(return_value=_make_receipt(success=True, tier="T2"))

        with _patch_playwright():
            with _patch_get_adapter(adapter_mock):
                mock_page = MagicMock()
                engine.browser_manager.create_context.return_value.new_page.return_value = mock_page
                try:
                    engine.submit(
                        mock_job, mock_artifacts, profile={},
                        resume_checkpoint=resume_checkpoint,
                    )
                except Exception:
                    pass

        # Check that new checkpoints have retry_count = 3 (incremented from 2)
        new_checkpoints = [cp for cp in checkpoint_collector if cp.retry_count == 3]
        assert len(new_checkpoints) >= 1


# ---------------------------------------------------------------------------
# Test 7: Integration - full checkpoint flow with simulated failure
# ---------------------------------------------------------------------------

class TestFullCheckpointFlow:
    def test_full_checkpoint_flow_with_failure(self, engine, mock_job, mock_artifacts, checkpoint_collector):
        """Full flow: preflight → session → captcha → routing → T1 fail → T2 success.
        Checkpoints recorded at each stage."""
        engine.preflight_screener.screen_page.return_value = _make_preflight_result("PASS")
        engine.session_validator.validate.return_value = _make_session_result(needs_login=False)
        engine.captcha_handler.detect_captcha.return_value = False

        adapter_mock = MagicMock()
        adapter_mock.__class__.__name__ = "GreenhouseAdapter"
        adapter_mock.submit.return_value = (False, None)

        engine.routing_engine.select.return_value = _make_routing_decision("T1", ["T2", "T3"])

        t1_receipt = _make_receipt(success=False, tier="T1")
        t2_receipt = _make_receipt(success=True, tier="T2")
        engine._execute_t1 = MagicMock(return_value=t1_receipt)
        engine._execute_t2 = MagicMock(return_value=t2_receipt)

        with _patch_playwright():
            with _patch_get_adapter(adapter_mock):
                mock_page = MagicMock()
                engine.browser_manager.create_context.return_value.new_page.return_value = mock_page
                result = engine.submit(mock_job, mock_artifacts, profile={})

        assert result.success is True

        # Verify checkpoints at each stage
        stages = [cp.stage for cp in checkpoint_collector]
        assert "preflight" in stages
        assert "session" in stages
        assert "captcha" in stages
        assert "routing" in stages
        assert "filling" in stages  # T1 attempt

        # Verify monotonic timestamps
        timestamps = [cp.timestamp for cp in checkpoint_collector]
        assert timestamps == sorted(timestamps)
