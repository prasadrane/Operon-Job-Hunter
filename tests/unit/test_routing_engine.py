"""Unit tests for RoutingEngine — T1/T2/T3 tier selection for submission routing."""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _get_classes():
    """Import RoutingEngine, TierDecision, TierExhaustedError via importlib.
    Clears any stub modules that may have been installed by other test files."""
    # Clear stubs installed by test_submission_tiers.py (parallel orchestration)
    for mod_key in list(sys.modules.keys()):
        if mod_key in (
            "src.pipeline.4_submission.routing_engine",
            "src.pipeline.4_submission.session_validator",
        ):
            mod = sys.modules.get(mod_key)
            if mod is None:
                continue
            # If it's a stub (has _Stub prefix classes), remove it
            re_cls = getattr(mod, "RoutingEngine", None)
            if re_cls is not None and "_Stub" in re_cls.__name__:
                del sys.modules[mod_key]

    re_mod = importlib.import_module("src.pipeline.4_submission.routing_engine")
    # Force reload if module was previously loaded as stub
    re_cls = getattr(re_mod, "RoutingEngine", None)
    if re_cls is not None and "_Stub" in re_cls.__name__:
        # Remove and reimport
        del sys.modules["src.pipeline.4_submission.routing_engine"]
        re_mod = importlib.import_module("src.pipeline.4_submission.routing_engine")
    bu_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
    return re_mod.RoutingEngine, re_mod.TierDecision, bu_mod.TierExhaustedError


@pytest.fixture
def routing_engine():
    RoutingEngine, TierDecision, TierExhaustedError = _get_classes()
    return RoutingEngine()


# ── Known ATS → T1 ───────────────────────────────────────────────────────────


def test_routing_known_ats_greenhouse():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    decision = engine.select("greenhouse", "https://boards.greenhouse.io/techjobs/123")
    assert decision.tier == "T1"
    assert decision.engine_name == "FastPath"


def test_routing_known_ats_lever():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    decision = engine.select("lever", "https://jobs.lever.co/company/abc")
    assert decision.tier == "T1"
    assert decision.engine_name == "FastPath"


def test_routing_known_ats_ashby():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    decision = engine.select("ashby", "https://jobs.ashbyhq.com/company/xyz")
    assert decision.tier == "T1"
    assert decision.engine_name == "FastPath"


def test_routing_known_ats_workday():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    decision = engine.select("workday", "https://myworkdayjobs.com/company/job")
    assert decision.tier == "T1"
    assert decision.engine_name == "FastPath"


# ── Unknown portal → T2 ──────────────────────────────────────────────────────


def test_routing_unknown_portal():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    decision = engine.select("unknown", "https://some-random-portal.com/job/1")
    assert decision.tier == "T2"
    assert decision.engine_name == "BrowserUse"


# ── T1 disabled → T2 ─────────────────────────────────────────────────────────


def test_routing_t1_disabled():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine(t1_enabled=False)
    decision = engine.select("greenhouse", "https://boards.greenhouse.io/techjobs/123")
    assert decision.tier == "T2"
    assert decision.engine_name == "BrowserUse"


# ── T2 disabled unknown → T3 ─────────────────────────────────────────────────


def test_routing_t2_disabled_unknown():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine(t2_enabled=False)
    decision = engine.select("unknown", "https://some-random-portal.com/job/1")
    assert decision.tier == "T3"
    assert decision.engine_name == "WebSurfer"


# ── All disabled → TierExhaustedError ────────────────────────────────────────


def test_routing_all_disabled():
    RoutingEngine, _, TierExhaustedError = _get_classes()
    engine = RoutingEngine(t1_enabled=False, t2_enabled=False, t3_enabled=False)
    with pytest.raises(TierExhaustedError):
        engine.select("greenhouse", "https://boards.greenhouse.io/techjobs/123")


# ── Fallback chain ────────────────────────────────────────────────────────────


def test_get_fallback_from_t1():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    fallback = engine.get_fallback("T1")
    assert fallback is not None
    assert fallback.tier == "T2"
    assert fallback.engine_name == "BrowserUse"


def test_get_fallback_from_t2():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    fallback = engine.get_fallback("T2")
    assert fallback is not None
    assert fallback.tier == "T3"
    assert fallback.engine_name == "WebSurfer"


def test_get_fallback_from_t3():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    fallback = engine.get_fallback("T3")
    assert fallback is None


# ── URL detection ─────────────────────────────────────────────────────────────


def test_url_detection_greenhouse():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    # portal_type is "unknown", but URL contains greenhouse.io → should detect
    decision = engine.select("unknown", "https://boards.greenhouse.io/techjobs/123")
    assert decision.tier == "T1"
    assert "greenhouse" in decision.reason.lower() or "T1" in decision.reason


def test_url_detection_unknown():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    decision = engine.select("unknown", "https://some-random-portal.com/job/1")
    # Should not detect as known ATS
    assert decision.tier == "T2"


# ── Fallback chain in decision ────────────────────────────────────────────────


def test_fallback_chain_in_decision():
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    decision = engine.select("greenhouse", "https://boards.greenhouse.io/techjobs/123")
    assert decision.fallback_chain == ["T2", "T3"]


# ── Config integration ────────────────────────────────────────────────────────


def test_config_defaults_via_getattr():
    """RoutingEngine uses getattr for settings — doesn't crash if attr missing."""
    RoutingEngine, _, _ = _get_classes()
    # Should not raise even if settings don't have submission_t* attributes
    engine = RoutingEngine()
    decision = engine.select("greenhouse", "https://boards.greenhouse.io/techjobs/123")
    assert decision.tier == "T1"


def test_constructor_overrides_config():
    """Constructor args override config defaults."""
    RoutingEngine, _, _ = _get_classes()
    # Even if config says t1_enabled=True, constructor can disable it
    engine = RoutingEngine(t1_enabled=False)
    decision = engine.select("greenhouse", "https://boards.greenhouse.io/techjobs/123")
    assert decision.tier == "T2"


# ── Generic portal_type detection from URL ────────────────────────────────────


def test_generic_portal_type_detected_from_url():
    """When portal_type is 'generic', detect from URL."""
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine()
    decision = engine.select("generic", "https://jobs.lever.co/acme/abc-123")
    assert decision.tier == "T1"
    assert decision.engine_name == "FastPath"


def test_fallback_chain_t2_has_only_t3():
    """T2 decision fallback chain should only include T3."""
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine(t1_enabled=False)
    decision = engine.select("unknown", "https://random-portal.com/job")
    assert decision.tier == "T2"
    assert decision.fallback_chain == ["T3"]


def test_fallback_chain_t3_is_empty():
    """T3 decision fallback chain should be empty."""
    RoutingEngine, _, _ = _get_classes()
    engine = RoutingEngine(t2_enabled=False)
    decision = engine.select("unknown", "https://random-portal.com/job")
    assert decision.tier == "T3"
    assert decision.fallback_chain == []
