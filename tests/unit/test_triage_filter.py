"""Unit tests for Stage 0 TriageFilter: TF-IDF scoring, VIP bypass, audit queue, auto-decay."""

import importlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_module():
    """Load triage_filter directly, bypassing 1_discovery __init__.py."""
    mod_name = "src.pipeline.1_discovery.triage_filter"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    proj_root = Path(__file__).resolve().parents[2]
    mod_path = proj_root / "src" / "pipeline" / "1_discovery" / "triage_filter.py"
    spec = importlib.util.spec_from_file_location(mod_name, str(mod_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load_module()


@pytest.fixture
def triage(mod):
    return mod.TriageFilter(threshold=0.15)


# ---------------------------------------------------------------------------
# VIP watchlist bypass
# ---------------------------------------------------------------------------

class TestVIPBypass:
    @pytest.fixture(autouse=True)
    def setup_vip(self, mod):
        mod._VIP_COMPANIES.add("salesforce")

    def test_vip_company_bypasses_triage(self, triage, mod):
        """VIP company returns 'pass' regardless of score."""
        # Even if predict would score low, is_vip_bypass gates first
        assert mod.is_vip_bypass("Salesforce") is True
        assert mod.is_vip_bypass("salesforce") is True  # case-insensitive

    def test_non_vip_company_not_bypassed(self, triage, mod):
        """Unknown company is not VIP."""
        assert mod.is_vip_bypass("random_startup_xyz") is False

    def test_predict_returns_pass_for_vip_regardless_of_score(self, triage, mod):
        """VIP company short-circuits predict to 'pass'."""
        # Irrelevant JD that should score near zero
        jd = "Make coffee and fetch lunch orders."
        score, decision = triage.predict(jd, company="Salesforce")
        assert decision == "pass"


# ---------------------------------------------------------------------------
# Score → decision mapping
# ---------------------------------------------------------------------------

class TestScoreDecision:
    def test_score_below_threshold_drops(self, triage):
        """Score < 0.15 → 'drop'."""
        with patch.object(triage, "_score", return_value=0.05):
            score, decision = triage.predict("some irrelevant text")
        assert score == 0.05
        assert decision == "drop"

    def test_score_in_flag_band(self, triage):
        """0.15 ≤ score < 0.40 → 'flag'."""
        with patch.object(triage, "_score", return_value=0.25):
            score, decision = triage.predict("some text")
        assert score == 0.25
        assert decision == "flag"

    def test_score_at_upper_boundary_passes(self, triage):
        """Score ≥ 0.40 → 'pass'."""
        with patch.object(triage, "_score", return_value=0.40):
            score, decision = triage.predict("some text")
        assert score == 0.40
        assert decision == "pass"

    def test_score_at_lower_boundary_flags(self, triage):
        """Score exactly 0.15 → 'flag' (not drop)."""
        with patch.object(triage, "_score", return_value=0.15):
            _, decision = triage.predict("x")
        assert decision == "flag"

    def test_score_just_below_upper_boundary_flags(self, triage):
        """Score 0.399 → 'flag'."""
        with patch.object(triage, "_score", return_value=0.399):
            _, decision = triage.predict("x")
        assert decision == "flag"


# ---------------------------------------------------------------------------
# Audit queue — 5% sampling
# ---------------------------------------------------------------------------

class TestAuditQueue:
    def test_log_audit_sample_called_for_dropped_jobs(self, triage, tmp_path):
        """Dropped jobs are logged to audit queue."""
        audit_log = tmp_path / "audit.jsonl"
        job = {"job_id": "J1", "title": "x", "description": "irrelevant"}
        triage.log_audit_sample(job, 0.05, path=str(audit_log))
        assert audit_log.exists()
        lines = audit_log.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["job_id"] == "J1"
        assert entry["score"] == 0.05

    def test_5_percent_sampling_rate(self, mod):
        """~5% of dropped jobs should be sampled (probabilistic)."""
        triage = mod.TriageFilter(threshold=0.15)
        sampled = sum(1 for _ in range(10000) if triage._should_audit_sample())
        rate = sampled / 10000
        assert 0.03 <= rate <= 0.07, f"sampling rate {rate} outside 3-7% band"


# ---------------------------------------------------------------------------
# Auto-decay
# ---------------------------------------------------------------------------

class TestAutoDecay:
    def test_decay_reduces_threshold(self, triage):
        """update_threshold(0.006) decays τ from 0.15 to 0.12."""
        assert triage.threshold == 0.15
        triage.update_threshold(0.006)
        assert triage.threshold == pytest.approx(0.12)

    def test_decay_does_not_go_below_minimum(self, triage):
        """Threshold floor is 0.05."""
        for _ in range(50):
            triage.update_threshold(0.01)
        assert triage.threshold >= 0.05

    def test_decay_only_triggers_above_fnr_threshold(self, triage):
        """FNR ≤ 0.005 should NOT trigger decay."""
        original = triage.threshold
        triage.update_threshold(0.003)
        assert triage.threshold == original

    def test_six_hour_cooldown(self, triage):
        """Second decay within 6h is suppressed."""
        triage.update_threshold(0.006)
        assert triage.threshold == pytest.approx(0.12)
        # Immediate second call — cooldown active
        triage.update_threshold(0.006)
        assert triage.threshold == pytest.approx(0.12)

    def test_decay_after_cooldown_expires(self, triage):
        """Decay allowed again after 6h cooldown."""
        triage.update_threshold(0.006)
        # Manually backdate the cooldown
        triage._last_decay_time = datetime.utcnow() - timedelta(hours=7)
        triage.update_threshold(0.006)
        assert triage.threshold == pytest.approx(0.09)

    def test_decay_dispatches_telegram_alert(self, triage, mod):
        """Auto-decay dispatches Telegram alert."""
        mock_dispatch = MagicMock()
        with patch.object(mod, "_dispatch_telegram_alert", mock_dispatch):
            triage.update_threshold(0.006)
        mock_dispatch.assert_called_once()

    def test_decay_dispatches_sse_event(self, triage, mod):
        """Auto-decay emits SSE event 'alert_triage_decay_triggered'."""
        mock_emit = MagicMock()
        with patch.object(mod, "_emit_sse_event", mock_emit):
            triage.update_threshold(0.006)
        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        assert call_args[0][0] == "alert_triage_decay_triggered"


# ---------------------------------------------------------------------------
# TF-IDF model init
# ---------------------------------------------------------------------------

class TestTFIDFInit:
    def test_init_loads_model(self, mod):
        """TriageFilter loads TF-IDF model at init."""
        tf = mod.TriageFilter(threshold=0.15)
        assert hasattr(tf, "tfidf")
        assert hasattr(tf, "clf")

    def test_predict_returns_tuple(self, triage):
        """predict returns (float, str)."""
        result = triage.predict("senior python engineer distributed systems")
        assert isinstance(result, tuple)
        assert len(result) == 2
        score, decision = result
        assert isinstance(score, float)
        assert decision in {"drop", "flag", "pass"}
