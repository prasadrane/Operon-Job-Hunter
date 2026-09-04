"""Integration tests for T1→T2→T3 tiered routing in SubmitterEngine.

Task 3 of P2b: verify SubmitterEngine correctly wires RoutingEngine,
SessionValidator, and BrowserUseSubmissionAgent into a fallback chain.
"""

import importlib
import sys
import types
import uuid
from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import CandidateProfile, JobPosting, SubmissionReceipt, TailoredArtifacts


# --- Stubs for parallel-built modules (RoutingEngine + SessionValidator) ---
# These mimic what Task 1 / Task 2 subagents will create. We install them
# into sys.modules BEFORE importing SubmitterEngine so importlib picks them up.

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
    """RoutingEngine stub — tests configure .decision before each run."""

    def __init__(self, decision: Optional[TierDecision] = None) -> None:
        self.decision = decision or TierDecision(tier="T1", reason="known", fallback_chain=["T2", "T3"])
        self.select_calls: list = []

    def select(self, portal_type: str, url: str, page) -> TierDecision:  # noqa: ARG002
        self.select_calls.append((portal_type, url, page))
        return self.decision


class _StubSessionValidator:
    """SessionValidator stub — tests configure .result before each run."""

    def __init__(self, result: Optional[SessionValidationResult] = None) -> None:
        self.result = result or SessionValidationResult(needs_login=False, session_valid=True)
        self.validate_calls: list = []

    def validate(self, url: str, portal_name: str, page) -> SessionValidationResult:  # noqa: ARG002
        self.validate_calls.append((url, portal_name, page))
        return self.result


def _install_stub_modules() -> None:
    """Register fake routing_engine / session_validator modules in sys.modules.

    Only install if the real module isn't already available — this prevents
    clobbering the real module when test ordering runs this file before other
    test files that depend on the real SessionValidator (e.g. test_session_validator.py).
    """
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


_install_stub_modules()


# --- Import SUT after stubs registered ---
se_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
SubmitterEngine = se_mod.SubmitterEngine


# --- Helpers / Fixtures ---

@pytest.fixture
def sample_profile():
    return CandidateProfile(
        first_name="Alex", last_name="Rivera", full_name="Alex Rivera",
        email="p@example.com", phone="+15550000000", location="Chicago, IL",
        address="123 Main", city="Chicago", state="IL", zip_code="60601",
        linkedin="", github="", portfolio="", website="",
        password="Test1234!", us_work_authorized=True, requires_sponsorship=False,
    )


@pytest.fixture
def sample_job():
    return JobPosting(
        id="job_tier_001", company="Acme", title="Staff Engineer",
        url="https://boards.greenhouse.io/acme/jobs/123",
        portal_type="greenhouse",
    )


@pytest.fixture
def sample_artifacts(tmp_path):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    cl = tmp_path / "cover.pdf"
    cl.write_bytes(b"%PDF-1.4 fake")
    return TailoredArtifacts(resume_pdf_path=str(pdf), cover_letter_path=str(cl))


def _build_engine(
    router: _StubRoutingEngine,
    session_val: _StubSessionValidator,
    adapter,
    *,
    adapter_submit_return=(True, "CONF-123"),
    fastpath_raises: bool = False,
    browser_use_result=None,
    receipts_dir: str = "./output/test_receipts",
):
    """Construct SubmitterEngine with fully-mocked collaborators."""
    bm = MagicMock()
    mock_page = MagicMock()
    mock_page.goto = MagicMock()
    mock_page.screenshot = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    bm.create_context.return_value = mock_context

    ch = MagicMock()
    ch.detect_captcha.return_value = False

    pf = MagicMock()
    pf_mod = importlib.import_module("src.pipeline.4_submission.preflight_screener")
    pf_res = MagicMock()
    pf_res.status = pf_mod.PreflightStatus.PASSED
    pf_res.has_status_screening_warning = False
    pf_res.has_prohibited_content_warning = False
    pf.screen_page.return_value = pf_res

    fp = MagicMock()
    if fastpath_raises:
        fp.fill_profile.side_effect = RuntimeError("fastpath boom")

    qa = MagicMock()

    # Wire adapter to return configured value
    adapter.submit = MagicMock(return_value=adapter_submit_return)

    # BrowserUse agent (async)
    bua = AsyncMock()
    if browser_use_result is not None:
        bua.submit.return_value = browser_use_result
    else:
        bu_result_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
        bua.submit.return_value = bu_result_mod.SubmissionResult(
            success=True, confirmation_id="BU-CONF-1", tier_used="T2",
        )

    engine = SubmitterEngine(
        browser_manager=bm,
        captcha_handler=ch,
        preflight_screener=pf,
        qa_synthesizer=qa,
        fastpath_submitter=fp,
        routing_engine=router,
        session_validator=session_val,
        browser_use_agent=bua,
        receipts_dir=receipts_dir,
    )
    return engine, adapter, mock_page, bua


@pytest.fixture(autouse=True)
def patch_adapter_and_audit(tmp_path, monkeypatch):
    """Patch get_adapter + log_audit globally for these tests."""
    adapter = MagicMock()
    adapter.__class__.__name__ = "GreenhouseAdapter"
    adapter.fill_form = MagicMock()
    adapter.submit = MagicMock(return_value=(True, "CONF-123"))

    def _get_adapter(url, page):  # noqa: ARG001
        return adapter

    adapters_pkg = importlib.import_module("src.pipeline.4_submission.adapters")
    monkeypatch.setattr(adapters_pkg, "get_adapter", _get_adapter)
    # Also patch the name already imported into submitter_engine's namespace
    monkeypatch.setattr(se_mod, "get_adapter", _get_adapter)
    # No-op audit so tests don't touch SQLite
    audit_mod = importlib.import_module("src.pipeline.4_submission.submission_audit")
    _noop_audit = lambda **kwargs: MagicMock()
    monkeypatch.setattr(audit_mod, "log_audit", _noop_audit)
    monkeypatch.setattr(se_mod, "log_audit", _noop_audit)
    # Store adapter ref so tests can mutate return values
    return {"adapter": adapter}


# --- Tests ---

def test_t1_routing_greenhouse(sample_job, sample_artifacts, sample_profile, patch_adapter_and_audit):
    """T1 path: known portal (greenhouse) uses FastPath + adapter."""
    router = _StubRoutingEngine(TierDecision(tier="T1", reason="known_ats", fallback_chain=["T2", "T3"]))
    sv = _StubSessionValidator()
    engine, adapter, mock_page, bua = _build_engine(router, sv, patch_adapter_and_audit['adapter'])

    receipt = engine.submit(sample_job, sample_artifacts, sample_profile)

    assert isinstance(receipt, SubmissionReceipt)
    assert receipt.success is True
    assert receipt.portal_type == "GreenhouseAdapter"
    # T1 path uses adapter, NOT browser_use
    adapter.submit.assert_called_once()
    bua.submit.assert_not_called()
    assert len(router.select_calls) == 1


def test_t2_routing_unknown(sample_job, sample_artifacts, sample_profile, patch_adapter_and_audit):
    """T2 path: unknown portal goes straight to BrowserUse."""
    router = _StubRoutingEngine(TierDecision(tier="T2", reason="unknown_portal", fallback_chain=["T3"]))
    sv = _StubSessionValidator()
    engine, adapter, mock_page, bua = _build_engine(router, sv, patch_adapter_and_audit['adapter'])

    receipt = engine.submit(sample_job, sample_artifacts, sample_profile)

    assert receipt.success is True
    # T2 does NOT call adapter.submit
    adapter.submit.assert_not_called()
    # T2 calls browser_use_agent
    bua.submit.assert_called_once()


def test_t1_failure_escalates_to_t2(sample_job, sample_artifacts, sample_profile, patch_adapter_and_audit):
    """T1 failure (adapter.submit returns success=False) triggers T2 fallback."""
    patch_adapter_and_audit["adapter"].submit.return_value = (False, None)
    router = _StubRoutingEngine(TierDecision(tier="T1", reason="known_ats", fallback_chain=["T2", "T3"]))
    sv = _StubSessionValidator()

    bu_result_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
    bu_ok = bu_result_mod.SubmissionResult(
        success=True, confirmation_id="BU-RESCUED", tier_used="T2",
    )

    engine, adapter, mock_page, bua = _build_engine(
        router, sv, patch_adapter_and_audit['adapter'],
        adapter_submit_return=(False, None),
        browser_use_result=bu_ok,
    )

    receipt = engine.submit(sample_job, sample_artifacts, sample_profile)

    # T1 attempted and failed
    adapter.submit.assert_called_once()
    # T2 rescued
    bua.submit.assert_called_once()
    assert receipt.success is True
    assert receipt.confirmation_id == "BU-RESCUED"


def test_t2_failure_escalates_to_t3(sample_job, sample_artifacts, sample_profile, patch_adapter_and_audit):
    """T2 failure triggers T3 WebSurfer fallback."""
    router = _StubRoutingEngine(TierDecision(tier="T2", reason="unknown_portal", fallback_chain=["T3"]))
    sv = _StubSessionValidator()

    bu_result_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
    bu_fail = bu_result_mod.SubmissionResult(
        success=False, error_message="T2 failed", tier_used="T2",
    )

    engine, adapter, mock_page, bua = _build_engine(
        router, sv, patch_adapter_and_audit['adapter'],
        browser_use_result=bu_fail,
    )
    # T3 mock: patch WebSurferAgent via monkeypatch on the engine's module
    ws_mod = importlib.import_module("src.pipeline.4_submission.websurfer_agent")
    mock_ws_instance = MagicMock()
    mock_ws_instance.run.return_value = {"success": True, "confirmation_id": "WS-CONF"}

    original_init = se_mod.SubmitterEngine.__init__

    class _EngineWithWS(se_mod.SubmitterEngine):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._websurfer = mock_ws_instance

    # Replace engine class for this test
    engine_with_ws = _EngineWithWS(
        browser_manager=engine.browser_manager,
        captcha_handler=engine.captcha_handler,
        preflight_screener=engine.preflight_screener,
        qa_synthesizer=engine.qa_synthesizer,
        fastpath_submitter=engine.fastpath_submitter,
        routing_engine=router,
        session_validator=sv,
        browser_use_agent=bua,
        receipts_dir=engine.receipts_dir,
    )

    receipt = engine_with_ws.submit(sample_job, sample_artifacts, sample_profile)

    bua.submit.assert_called_once()
    mock_ws_instance.run.assert_called_once()
    assert receipt.success is True
    assert receipt.confirmation_id == "WS-CONF"


def test_session_expired_blocks_submission(sample_job, sample_artifacts, sample_profile, patch_adapter_and_audit):
    """Session validation failure (needs_login=True) short-circuits before captcha."""
    router = _StubRoutingEngine()
    sv = _StubSessionValidator(SessionValidationResult(
        needs_login=True, session_valid=False, reason="session_expired",
    ))
    engine, adapter, mock_page, bua = _build_engine(router, sv, patch_adapter_and_audit['adapter'])

    receipt = engine.submit(sample_job, sample_artifacts, sample_profile)

    assert receipt.success is False
    assert "expired" in (receipt.error_message or "").lower() or "login" in (receipt.error_message or "").lower()
    # Nothing past session validation should run
    adapter.submit.assert_not_called()
    bua.submit.assert_not_called()
    # Router never reached
    assert len(router.select_calls) == 0


def test_audit_logs_tier_selection(sample_job, sample_artifacts, sample_profile, monkeypatch):
    """route_select audit entry is emitted with tier metadata."""
    audit_calls = []

    def fake_audit(**kwargs):
        audit_calls.append(kwargs)
        return MagicMock()

    audit_mod = importlib.import_module("src.pipeline.4_submission.submission_audit")
    monkeypatch.setattr(audit_mod, "log_audit", fake_audit)
    monkeypatch.setattr(se_mod, "log_audit", fake_audit)
    adapter = MagicMock()
    adapter.__class__.__name__ = "GreenhouseAdapter"
    adapter.fill_form = MagicMock()
    adapter.submit = MagicMock(return_value=(True, "CONF-123"))
    adapters_pkg = importlib.import_module("src.pipeline.4_submission.adapters")
    _ga = lambda url, page: adapter
    monkeypatch.setattr(adapters_pkg, "get_adapter", _ga)
    monkeypatch.setattr(se_mod, "get_adapter", _ga)

    router = _StubRoutingEngine(TierDecision(tier="T1", reason="known_ats", fallback_chain=["T2"]))
    sv = _StubSessionValidator()
    engine, _, _, _ = _build_engine(router, sv, adapter)

    engine.submit(sample_job, sample_artifacts, sample_profile)

    route_select_calls = [c for c in audit_calls if c.get("action_type") == "route_select"]
    assert len(route_select_calls) >= 1
    assert route_select_calls[0]["tier"] == "T1"
    assert route_select_calls[0]["job_id"] == sample_job.id


def test_all_tiers_disabled(sample_job, sample_artifacts, sample_profile, patch_adapter_and_audit):
    """All 3 tiers fail → receipt has success=False with error message."""
    router = _StubRoutingEngine(TierDecision(tier="T1", reason="known_ats", fallback_chain=["T2", "T3"]))
    sv = _StubSessionValidator()

    bu_result_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
    bu_fail = bu_result_mod.SubmissionResult(
        success=False, error_message="T2 dead", tier_used="T2",
    )

    engine, adapter, mock_page, bua = _build_engine(
        router, sv, patch_adapter_and_audit['adapter'],
        adapter_submit_return=(False, None),
        browser_use_result=bu_fail,
    )

    # T3 WebSurfer also fails
    mock_ws = MagicMock()
    mock_ws.run.return_value = {"success": False, "error": "T3 dead"}

    class _E(se_mod.SubmitterEngine):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._websurfer = mock_ws

    engine2 = _E(
        browser_manager=engine.browser_manager,
        captcha_handler=engine.captcha_handler,
        preflight_screener=engine.preflight_screener,
        qa_synthesizer=engine.qa_synthesizer,
        fastpath_submitter=engine.fastpath_submitter,
        routing_engine=router,
        session_validator=sv,
        browser_use_agent=bua,
        receipts_dir=engine.receipts_dir,
    )

    receipt = engine2.submit(sample_job, sample_artifacts, sample_profile)

    assert receipt.success is False
    assert receipt.error_message is not None
