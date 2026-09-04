"""Unit tests for RetrospectiveAgent: Telemetry analysis, dynamic quirk learning, and digest generation."""

import importlib
import json
import os
import sqlite3
import pytest

from src.core.db.telemetry_sink import TelemetrySink
from src.core.memory.core_memory_manager import CoreMemoryManager

retro_mod = importlib.import_module("src.pipeline.5_lifecycle.retrospective_agent")
RetrospectiveAgent = retro_mod.RetrospectiveAgent
SessionMetrics = retro_mod.SessionMetrics


@pytest.fixture
def test_env(tmp_path):
    """Create isolated SQLite telemetry DB and quirks path."""
    telemetry_db = tmp_path / "test_telemetry.db"
    quirks_json = tmp_path / "test_ats_quirks.json"

    with sqlite3.connect(str(telemetry_db)) as conn:
        conn.execute(
            """
            CREATE TABLE audit_spans (
                span_id TEXT,
                event TEXT,
                tokens INTEGER,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Seed test audit spans
        spans = [
            (
                "span_1",
                "form_submission_success",
                0,
                json.dumps({"company": "Capital One", "job_id": "job_101", "success": True, "latency_s": 4.2}),
            ),
            (
                "span_2",
                "form_healing_event",
                0,
                json.dumps({
                    "company": "Capital One",
                    "portal_type": "workday",
                    "field_name": "phone",
                    "original_selector": "#phone",
                    "healed_selector": "input[data-automation-id='phone-number']",
                    "action": "selector_recovery",
                    "details": "Auto-recovered from AXTree label match",
                }),
            ),
            (
                "span_3",
                "form_submission_success",
                0,
                json.dumps({"company": "Stripe", "job_id": "job_102", "success": True, "latency_s": 2.5}),
            ),
        ]
        conn.executemany("INSERT INTO audit_spans (span_id, event, tokens, metadata) VALUES (?, ?, ?, ?)", spans)
        conn.commit()

    return {"telemetry_db": str(telemetry_db), "quirks_json": str(quirks_json)}


def test_metrics_calculation(test_env):
    """Verify session metrics calculation from telemetry spans."""
    agent = RetrospectiveAgent(
        telemetry_path=test_env["telemetry_db"],
        quirks_path=test_env["quirks_json"],
    )
    metrics = agent.compute_session_metrics()

    assert metrics.total_submissions == 2
    assert metrics.successful_submissions == 2
    assert metrics.precision_score == 100.0
    assert metrics.healing_events_count == 1
    assert metrics.avg_latency_s == pytest.approx(3.35, 0.1)


def test_dynamic_quirk_extraction_and_persistence(test_env):
    """Verify extracted quirks from healing events are persisted to JSON."""
    agent = RetrospectiveAgent(
        telemetry_path=test_env["telemetry_db"],
        quirks_path=test_env["quirks_json"],
    )
    learned_quirks = agent.extract_and_persist_quirks()

    assert len(learned_quirks) == 1
    assert "Capital One" in learned_quirks
    assert learned_quirks["Capital One"]["phone"]["healed_selector"] == "input[data-automation-id='phone-number']"

    # Verify JSON file written to disk
    assert os.path.exists(test_env["quirks_json"])
    with open(test_env["quirks_json"], "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["Capital One"]["phone"]["healed_selector"] == "input[data-automation-id='phone-number']"


def test_session_digest_markdown_generation(test_env):
    """Verify generation of human-readable Markdown retrospective digest."""
    agent = RetrospectiveAgent(
        telemetry_path=test_env["telemetry_db"],
        quirks_path=test_env["quirks_json"],
    )
    digest_md = agent.generate_retrospective_digest()

    assert "# Session Retrospective & Self-Learning Digest" in digest_md
    assert "**Precision Score:** 100.0%" in digest_md
    assert "Capital One" in digest_md
    assert "input[data-automation-id='phone-number']" in digest_md
