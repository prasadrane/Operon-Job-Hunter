"""Integration tests for PipelineGraphState + SubmitterEngine credential_ref integration.

Contract: credential_ref flows from state → submit() → vault lookup → tier execution.
Credentials never stored in state or logged.

Mirrors the stub/fixture pattern from test_submission_tiers.py so both test files
can coexist without colliding on sys.modules.
"""
import importlib
import logging
import sys
import types
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import JobPosting, SubmissionReceipt
from src.pipeline.state_schema import PipelineGraphState


# ── Stub vault classes ────────────────────────────────────────────────────────

@dataclass
class FakeCredentialEntry:
    username: str
    password: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class FakeCredentialVault:
    def __init__(self, store: Optional[Dict[str, FakeCredentialEntry]] = None):
        self._store = store or {}

    def get_credentials(self, portal_type: str) -> Optional[FakeCredentialEntry]:
        return self._store.get(portal_type)


# ── Stub routing / session modules (only if real ones aren't available) ───────

@dataclass
class _TierDecision:
    tier: str = "T2"
    reason: str = "test"
    fallback_chain: List[str] = None

    def __post_init__(self):
        if self.fallback_chain is None:
            self.fallback_chain = ["T3"]


class _StubRoutingEngine:
    def __init__(self, decision=None):
        self.decision = decision or _TierDecision()

    def select(self, **kwargs):
        return self.decision


class _StubSessionValidator:
    def validate(self, url, portal_name, page):
        @dataclass
        class R:
            needs_login: bool = False
            error: Optional[str] = None
        return R()


def _install_stub_modules():
    """Install minimal stubs for digit-dir modules that SubmitterEngine imports."""
    try:
        importlib.import_module("src.pipeline.4_submission.routing_engine")
    except Exception:
        re_mod = types.ModuleType("src.pipeline.4_submission.routing_engine")
        re_mod.RoutingEngine = _StubRoutingEngine
        re_mod.TierDecision = _TierDecision
        sys.modules["src.pipeline.4_submission.routing_engine"] = re_mod

    try:
        importlib.import_module("src.pipeline.4_submission.session_validator")
    except Exception:
        sv_mod = types.ModuleType("src.pipeline.4_submission.session_validator")
        sv_mod.SessionValidator = _StubSessionValidator
        sys.modules["src.pipeline.4_submission.session_validator"] = sv_mod


_install_stub_modules()

# Import SubmitterEngine after stubs installed
se_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
SubmitterEngine = se_mod.SubmitterEngine


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_job(**overrides) -> JobPosting:
    base = dict(
        id="job-cred-001",
        title="SWE",
        company="Acme",
        url="https://boards.greenhouse.io/acme/1",
        portal_type="greenhouse",
    )
    base.update(overrides)
    return JobPosting(**base)


def _build_engine(router=None, browser_use_agent=None):
    """Construct SubmitterEngine with MagicMock collaborators (same pattern as test_submission_tiers)."""
    bm = MagicMock()
    mock_page = MagicMock()
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
    qa = MagicMock()
    sv = _StubSessionValidator()
    router = router or _StubRoutingEngine(_TierDecision(tier="T2", reason="test", fallback_chain=["T3"]))
    bua = browser_use_agent or AsyncMock()

    return SubmitterEngine(
        browser_manager=bm,
        captcha_handler=ch,
        preflight_screener=pf,
        qa_synthesizer=qa,
        fastpath_submitter=fp,
        routing_engine=router,
        session_validator=sv,
        browser_use_agent=bua,
        receipts_dir="./output/test_cred_receipts",
    ), mock_page


@pytest.fixture(autouse=True)
def _patch_adapter_and_audit(monkeypatch, tmp_path):
    """Patch get_adapter + log_audit for all tests in this module."""
    adapter = MagicMock()
    adapter.__class__.__name__ = "GreenhouseAdapter"
    adapter.fill_form = MagicMock()
    adapter.submit = MagicMock(return_value=(True, "CONF-123"))

    def _get_adapter(url, page):
        return adapter

    adapters_pkg = importlib.import_module("src.pipeline.4_submission.adapters")
    monkeypatch.setattr(adapters_pkg, "get_adapter", _get_adapter)
    monkeypatch.setattr(se_mod, "get_adapter", _get_adapter)

    _noop_audit = lambda **kwargs: MagicMock()
    audit_mod = importlib.import_module("src.pipeline.4_submission.submission_audit")
    monkeypatch.setattr(audit_mod, "log_audit", _noop_audit)
    monkeypatch.setattr(se_mod, "log_audit", _noop_audit)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_submit_with_credential_ref(monkeypatch):
    """credential_ref triggers vault lookup; credentials flow to SubmissionTask."""
    vault = FakeCredentialVault({
        "greenhouse": FakeCredentialEntry("user@acme.com", "s3cret", {"portal_url": "https://gh.com"}),
    })
    monkeypatch.setattr(se_mod, "CredentialVault", lambda: vault, raising=False)

    bua = AsyncMock()
    bu_result_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
    bua.submit.return_value = bu_result_mod.SubmissionResult(
        success=True, confirmation_id="BU-CONF-1", tier_used="T2",
    )
    engine, _ = _build_engine(browser_use_agent=bua)

    job = _make_job()
    receipt = engine.submit(job, credential_ref="greenhouse")

    assert receipt.success is True
    # Check that submit() was called with a SubmissionTask carrying credentials
    call_args = bua.submit.call_args
    task = call_args[0][0] if call_args[0] else call_args[1].get("task")
    assert task.credentials is not None
    assert task.credentials["username"] == "user@acme.com"
    assert task.credentials["password"] == "s3cret"
    assert task.credentials["portal_url"] == "https://gh.com"


def test_submit_without_credential_ref(monkeypatch):
    """No credential_ref → credentials=None in SubmissionTask (back-compat)."""
    vault = FakeCredentialVault({})
    monkeypatch.setattr(se_mod, "CredentialVault", lambda: vault, raising=False)

    bua = AsyncMock()
    bu_result_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
    bua.submit.return_value = bu_result_mod.SubmissionResult(
        success=True, confirmation_id="BU-CONF", tier_used="T2",
    )
    engine, _ = _build_engine(browser_use_agent=bua)

    job = _make_job()
    receipt = engine.submit(job)  # no credential_ref

    assert receipt.success is True
    call_args = bua.submit.call_args
    task = call_args[0][0] if call_args[0] else call_args[1].get("task")
    assert task.credentials is None


def test_credential_ref_not_in_state():
    """PipelineGraphState holds only the reference string, never credentials."""
    state = PipelineGraphState(
        job_id="j1", company="Acme", title="SWE",
        url="https://x.com/1", portal_type="greenhouse",
        fit_score=80.0, current_stage="submission",
        is_ghost_job=False, work_auth_blocker=False,
        evaluation_warning=False,
        credential_ref="greenhouse",
    )
    assert state.get("credential_ref") == "greenhouse"
    for sensitive in ("password", "username", "credentials"):
        assert sensitive not in state
    # credential_ref is a reference string, never a blob
    assert isinstance(state["credential_ref"], str)


def test_vault_unavailable_graceful(monkeypatch):
    """Vault returns None for ref → submit proceeds with credentials=None."""
    vault = FakeCredentialVault({})  # empty store
    monkeypatch.setattr(se_mod, "CredentialVault", lambda: vault, raising=False)

    bua = AsyncMock()
    bu_result_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
    bua.submit.return_value = bu_result_mod.SubmissionResult(
        success=True, confirmation_id="BU-CONF", tier_used="T2",
    )
    engine, _ = _build_engine(browser_use_agent=bua)

    job = _make_job()
    receipt = engine.submit(job, credential_ref="nonexistent_portal")

    assert receipt.success is True
    call_args = bua.submit.call_args
    task = call_args[0][0] if call_args[0] else call_args[1].get("task")
    assert task.credentials is None


def test_t2_receives_credentials(monkeypatch):
    """SubmissionTask.credentials == {username, password, **metadata}."""
    vault = FakeCredentialVault({
        "lever": FakeCredentialEntry("admin", "pw123", {"mfa_secret": "XYZ"}),
    })
    monkeypatch.setattr(se_mod, "CredentialVault", lambda: vault, raising=False)

    bua = AsyncMock()
    bu_result_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
    bua.submit.return_value = bu_result_mod.SubmissionResult(
        success=True, confirmation_id="BU-CONF", tier_used="T2",
    )
    engine, _ = _build_engine(browser_use_agent=bua)

    job = _make_job(portal_type="lever")
    engine.submit(job, credential_ref="lever")

    call_args = bua.submit.call_args
    task = call_args[0][0] if call_args[0] else call_args[1].get("task")
    assert task.credentials == {
        "username": "admin",
        "password": "pw123",
        "mfa_secret": "XYZ",
    }


def test_credentials_not_logged(monkeypatch, caplog):
    """Neither username nor password appear in any log record from submitter_engine."""
    vault = FakeCredentialVault({
        "greenhouse": FakeCredentialEntry("secret_user@corp.com", "hunter2_SUPER_secret"),
    })
    monkeypatch.setattr(se_mod, "CredentialVault", lambda: vault, raising=False)

    bua = AsyncMock()
    bu_result_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
    bua.submit.return_value = bu_result_mod.SubmissionResult(
        success=True, confirmation_id="BU-CONF", tier_used="T2",
    )
    engine, _ = _build_engine(browser_use_agent=bua)

    job = _make_job()
    with caplog.at_level(logging.DEBUG, logger="src.pipeline._4_submission.submitter_engine"):
        engine.submit(job, credential_ref="greenhouse")

    full_log = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "secret_user@corp.com" not in full_log
    assert "hunter2_SUPER_secret" not in full_log
