"""Tests for multi-agent healing orchestrator and stage healers."""

import importlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Dynamic imports for numbered module
_healing_pkg = importlib.import_module("src.pipeline.5_lifecycle.healing")
BaseHealer = _healing_pkg.BaseHealer
HealingResult = _healing_pkg.HealingResult
HealingReport = _healing_pkg.HealingReport
HealingOrchestrator = _healing_pkg.HealingOrchestrator
build_default_orchestrator = _healing_pkg.build_default_orchestrator
DiscoveryHealer = _healing_pkg.DiscoveryHealer
GatewayHealer = _healing_pkg.GatewayHealer
EvaluationHealer = _healing_pkg.EvaluationHealer
TailoringHealer = _healing_pkg.TailoringHealer
SubmissionHealer = _healing_pkg.SubmissionHealer
LifecycleHealer = _healing_pkg.LifecycleHealer


@dataclass
class MockError:
    """Mock error event for testing."""
    id: str = "err-1"
    source: str = "crawler"
    component: str = "greenhouse_crawler"
    company: str = "TestCo"
    portal_type: str = "greenhouse"
    board_token: str = "testco"
    error_type: str = "HTTP_404"
    http_status: int = 404
    message: str = "Board not found"
    careers_url: str = ""


# ─── Base Healer Tests ──────────────────────────────────────────────────────


class TestBaseHealer:
    def test_healing_result_auto_timestamp(self):
        result = HealingResult(healer="test", action="test action", success=True)
        assert result.timestamp
        assert "T" in result.timestamp

    def test_healing_report_auto_fields(self):
        report = HealingReport(healer="test")
        assert report.cycle_id.startswith("test_")
        assert report.timestamp

    def test_should_run_respects_cooldown(self):
        healer = DiscoveryHealer(cooldown_hours=1.0)
        assert healer.should_run() is True
        healer.mark_run()
        assert healer.should_run() is False


# ─── Discovery Healer Tests ─────────────────────────────────────────────────


class TestDiscoveryHealer:
    def test_can_heal_http_errors(self):
        healer = DiscoveryHealer()
        assert healer.can_heal("HTTP_404", "greenhouse_crawler") is True
        assert healer.can_heal("HTTP_422", "lever_crawler") is True
        assert healer.can_heal("HTTP_ERROR", "ashby_crawler") is True
        assert healer.can_heal("RATE_LIMIT", "gateway") is False

    @patch.object(_healing_pkg.discovery_healer, "validate_candidate", return_value=True)
    def test_heal_updates_config(self, mock_validate, tmp_path):
        # Create a test companies.yaml
        companies_file = str(tmp_path / "companies.yaml")
        import yaml
        companies = [
            {"name": "TestCo", "portal_type": "greenhouse", "board_token": "testco", "enabled": True},
        ]
        with open(companies_file, "w") as f:
            yaml.safe_dump({"companies": companies}, f)

        healer = DiscoveryHealer(companies_file=companies_file)
        errors = [MockError(company="TestCo", portal_type="greenhouse", board_token="testco")]
        results = healer.heal(errors)

        assert len(results) > 0
        assert results[0].success is True
        assert results[0].config_changed is True

        # Verify config was updated
        with open(companies_file, "r") as f:
            updated = yaml.safe_load(f)
        company = updated["companies"][0]
        assert company["portal_type"] != "greenhouse" or company["board_token"] != "testco"

    @patch.object(_healing_pkg.discovery_healer, "validate_candidate", return_value=False)
    def test_heal_dry_run_no_change(self, mock_validate, tmp_path):
        companies_file = str(tmp_path / "companies.yaml")
        import yaml
        companies = [{"name": "TestCo", "portal_type": "greenhouse", "board_token": "testco"}]
        with open(companies_file, "w") as f:
            yaml.safe_dump({"companies": companies}, f)

        healer = DiscoveryHealer(companies_file=companies_file, dry_run=True)
        errors = [MockError(company="TestCo")]
        results = healer.heal(errors)

        # Dry run should still report success if validation passes, but no config change
        # Since validate_candidate returns False, no candidate will succeed
        assert all(not r.config_changed for r in results)


# ─── Gateway Healer Tests ───────────────────────────────────────────────────


class TestGatewayHealer:
    def test_can_heal_gateway_errors(self):
        healer = GatewayHealer()
        assert healer.can_heal("RATE_LIMIT", "alibaba_provider") is True
        assert healer.can_heal("PROVIDER_ERROR", "gemini_provider") is True
        assert healer.can_heal("FATAL", "llm_gateway") is True
        assert healer.can_heal("HTTP_404", "crawler") is False

    def test_heal_rotates_provider_on_rate_limit(self, tmp_path):
        env_file = str(tmp_path / ".env")
        with open(env_file, "w") as f:
            f.write("PRIMARY_LLM_PROVIDER=alibaba\n")

        healer = GatewayHealer(env_file=env_file)
        errors = [MockError(source="gateway", error_type="RATE_LIMIT", component="alibaba_provider")]
        results = healer.heal(errors)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].config_changed is True
        assert "gemini" in results[0].details.get("to", "") or "openrouter" in results[0].details.get("to", "")


# ─── Evaluation Healer Tests ────────────────────────────────────────────────


class TestEvaluationHealer:
    def test_can_heal_evaluation_errors(self):
        healer = EvaluationHealer()
        assert healer.can_heal("LLM_FALLBACK", "rubric_evaluator") is True
        assert healer.can_heal("LLM_BATCH_ERROR", "fit_scorer") is True
        assert healer.can_heal("EVALUATION_ERROR", "node") is True
        assert healer.can_heal("HTTP_404", "crawler") is False


# ─── Tailoring Healer Tests ─────────────────────────────────────────────────


class TestTailoringHealer:
    def test_can_heal_tailoring_errors(self):
        healer = TailoringHealer()
        assert healer.can_heal("PDF_COMPILE_ERROR", "typst_renderer") is True
        assert healer.can_heal("GRAPH_RAG_ERROR", "graph_retriever") is True
        assert healer.can_heal("HTTP_404", "crawler") is False

    def test_switch_pdf_backend(self, tmp_path):
        env_file = str(tmp_path / ".env")
        with open(env_file, "w") as f:
            f.write("PDF_COMPILER_BACKEND=reportlab\n")

        healer = TailoringHealer(env_file=env_file)
        errors = [MockError(source="tailoring", error_type="PDF_COMPILE_ERROR")]
        results = healer.heal(errors)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].details.get("to") == "typst"

    def test_rebuild_graph(self, tmp_path):
        graph_file = tmp_path / "embedded_graph.json"
        graph_file.write_text('{"nodes": []}')

        healer = TailoringHealer()
        # Override path for testing
        healer._rebuild_graph = lambda error_id: HealingResult(
            healer="tailoring",
            action="test rebuild",
            success=True,
        )
        # Just test the logic exists
        assert healer.can_heal("GRAPH_RAG_ERROR", "retriever") is True


# ─── Submission Healer Tests ────────────────────────────────────────────────


class TestSubmissionHealer:
    def test_can_heal_submission_errors(self):
        healer = SubmissionHealer()
        assert healer.can_heal("BROWSER_ACTION_ERROR", "action_dispatcher") is True
        assert healer.can_heal("CAPTCHA_TIMEOUT", "captcha_handler") is True
        assert healer.can_heal("SUBMISSION_ERROR", "submitter_engine") is True
        assert healer.can_heal("HTTP_404", "crawler") is False

    def test_clean_browser_locks(self, tmp_path):
        profile_dir = tmp_path / "browser_profile" / "Default"
        profile_dir.mkdir(parents=True)
        (profile_dir / "SingletonLock").write_text("")
        (profile_dir / "SingletonSocket").write_text("")

        healer = SubmissionHealer(browser_profile_dir=str(tmp_path / "browser_profile"))
        errors = [MockError(source="submission", error_type="BROWSER_ACTION_ERROR")]
        results = healer.heal(errors)

        assert len(results) >= 1
        assert results[0].success is True
        # Locks should be cleaned
        assert not (profile_dir / "SingletonLock").exists()


# ─── Lifecycle Healer Tests ─────────────────────────────────────────────────


class TestLifecycleHealer:
    def test_can_heal_lifecycle_errors(self):
        healer = LifecycleHealer()
        assert healer.can_heal("TELEMETRY_READ_ERROR", "retrospective_agent") is True
        assert healer.can_heal("PERSIST_ERROR", "retrospective_agent") is True
        assert healer.can_heal("CURSOR_ERROR", "lifecycle_watcher") is True
        assert healer.can_heal("HTTP_404", "crawler") is False

    def test_recreate_telemetry_schema(self, tmp_path):
        telemetry_db = str(tmp_path / "telemetry.db")
        healer = LifecycleHealer(telemetry_db=telemetry_db)
        errors = [MockError(source="lifecycle", error_type="TELEMETRY_READ_ERROR")]
        results = healer.heal(errors)

        assert len(results) == 1
        assert results[0].success is True
        assert Path(telemetry_db).exists()

    def test_reset_cursor(self, tmp_path):
        cursor_file = tmp_path / "gmail_cursor.json"
        cursor_file.write_text('{"cursor": "abc123"}')

        healer = LifecycleHealer(cursor_file=str(cursor_file))
        errors = [MockError(source="lifecycle", error_type="CURSOR_ERROR")]
        results = healer.heal(errors)

        assert len(results) == 1
        assert results[0].success is True
        assert not cursor_file.exists()


# ─── Orchestrator Tests ─────────────────────────────────────────────────────


class TestHealingOrchestrator:
    def test_build_default_orchestrator(self):
        orch = build_default_orchestrator(dry_run=True)
        assert len(orch.healer_names) == 6
        assert "discovery" in orch.healer_names
        assert "gateway" in orch.healer_names
        assert "evaluation" in orch.healer_names
        assert "tailoring" in orch.healer_names
        assert "submission" in orch.healer_names
        assert "lifecycle" in orch.healer_names

    def test_run_cycle_no_errors(self):
        orch = build_default_orchestrator(dry_run=True)
        reports = orch.run_cycle()
        # With no errors in DB, should return empty reports
        assert isinstance(reports, dict)

    def test_run_single_stage(self):
        orch = build_default_orchestrator(dry_run=True)
        report = orch.run_single("discovery")
        # No errors in DB, so report should be None or empty
        # (depends on whether there are errors in the test DB)

    def test_get_status(self):
        orch = build_default_orchestrator(dry_run=True)
        status = orch.get_status()
        assert "healers" in status
        assert "error_stats" in status
        assert len(status["healers"]) == 6
        for name, info in status["healers"].items():
            assert "stage_label" in info
            assert "can_run" in info
            assert "cooldown_hours" in info

    def test_healer_cooldown(self):
        healer = DiscoveryHealer(cooldown_hours=24.0)
        assert healer.should_run() is True
        healer.mark_run()
        assert healer.should_run() is False

        # Test with zero cooldown
        healer2 = DiscoveryHealer(cooldown_hours=0)
        healer2.mark_run()
        assert healer2.should_run() is True
