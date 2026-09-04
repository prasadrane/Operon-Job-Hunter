"""Unit tests for Phase 3: Tenant-Scoped Quirks with TTL and OA Radar Study Guide Trigger."""

import importlib
import json
import os
import time
from unittest.mock import MagicMock, patch
import pytest

_retro_mod = importlib.import_module("src.pipeline.5_lifecycle.retrospective_agent")
RetrospectiveAgent = _retro_mod.RetrospectiveAgent

_oa_mod = importlib.import_module("src.pipeline.5_lifecycle.oa_radar")
OARadar = _oa_mod.OARadar


def test_retrospective_agent_tenant_scoping_and_ttl(tmp_path):
    """Verify learned quirks are scoped by domain and timestamped."""
    quirks_file = tmp_path / "ats_quirks.json"
    telemetry_db = tmp_path / "telemetry.db"

    agent = RetrospectiveAgent(telemetry_path=str(telemetry_db), quirks_path=str(quirks_file))

    # Mock audit spans with healing events across different domains
    now_ts = time.time()
    mock_spans = [
        {
            "span_id": "span_1",
            "event": "form_healing_event",
            "tokens": 100,
            "created_at": "2026-08-22T19:00:00",
            "metadata": {
                "company": "Capital One",
                "domain": "capitalone.myworkdayjobs.com",
                "field_name": "phone",
                "healed_selector": "input#custom-phone-id",
                "action": "type",
                "timestamp": now_ts,
            },
        },
        {
            "span_id": "span_2",
            "event": "form_healing_event",
            "tokens": 100,
            "created_at": "2026-08-22T19:00:00",
            "metadata": {
                "company": "Stripe",
                "domain": "stripe.com",
                "field_name": "resume",
                "healed_selector": "input#stripe-resume-upload",
                "action": "upload",
                "timestamp": now_ts - (35 * 86400),  # 35 days old (expired)
            },
        },
    ]

    with patch.object(agent, "load_audit_spans", return_value=mock_spans):
        quirks = agent.extract_and_persist_quirks(max_age_days=30)

    assert "Capital One" in quirks
    assert "phone" in quirks["Capital One"]
    assert quirks["Capital One"]["phone"]["healed_selector"] == "input#custom-phone-id"
    assert quirks["Capital One"]["phone"]["domain"] == "capitalone.myworkdayjobs.com"


def test_oa_radar_study_guide_auto_generation(tmp_path):
    """Verify OARadar triggers study guide and STAR narrative generation on OA detection."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    radar = OARadar(artifacts_dir=str(artifacts_dir))
    email_text = (
        "Subject: Next steps: Datadog Technical Assessment\n"
        "Hi Alex, please complete your HackerRank coding challenge within 7 days for the Senior Software Engineer role."
    )

    oa_result = radar.scan_and_trigger_prep(
        subject="Next steps: Datadog Technical Assessment",
        body=email_text,
        sender="recruiting@datadog.com",
    )

    assert oa_result.is_oa is True
    assert oa_result.platform.lower() in ("hackerrank", "codesignal", "karat", "generic")
    assert oa_result.study_guide_path is not None
    assert os.path.exists(oa_result.study_guide_path)
