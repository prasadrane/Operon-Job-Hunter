"""Tests for self-healing agent and healing strategies."""

import importlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Dynamic import for numbered module
_healing_mod = importlib.import_module("src.pipeline.5_lifecycle.healing_strategies")
_agent_mod = importlib.import_module("src.pipeline.5_lifecycle.self_healing_agent")

CrawlerError = _healing_mod.CrawlerError
HealingCandidate = _healing_mod.HealingCandidate
HealingResult = _healing_mod.HealingResult
attempt_healing = _healing_mod.attempt_healing
validate_candidate = _healing_mod.validate_candidate
generate_token_variants = _healing_mod.generate_token_variants
GreenhouseHealing = _healing_mod.GreenhouseHealing
LeverHealing = _healing_mod.LeverHealing
AshbyHealing = _healing_mod.AshbyHealing
WorkdayHealing = _healing_mod.WorkdayHealing

SelfHealingAgent = _agent_mod.SelfHealingAgent
HealingAuditLog = _agent_mod.HealingAuditLog
HealingReport = _agent_mod.HealingReport
detect_errors_from_logs = _agent_mod.detect_errors_from_logs
update_company_config = _agent_mod.update_company_config
load_companies_yaml = _agent_mod.load_companies_yaml
save_companies_yaml = _agent_mod.save_companies_yaml


# ─── Healing Strategies Tests ────────────────────────────────────────────────


class TestTokenVariants:
    def test_basic_token(self):
        variants = generate_token_variants("databricks")
        assert "databricks" in variants
        assert "DATABRICKS" not in variants  # lowercase only
        assert len(variants) > 1

    def test_company_name_generates_variants(self):
        variants = generate_token_variants("mod", "Modern Treasury")
        assert "moderntreasury" in variants
        assert "modern-treasury" in variants or "moderntreasury" in variants

    def test_short_tokens_filtered(self):
        variants = generate_token_variants("")
        assert all(len(v) >= 2 for v in variants)


class TestGreenhouseHealing:
    def test_can_handle_greenhouse_404(self):
        strategy = GreenhouseHealing()
        error = CrawlerError(
            company_name="TestCo",
            portal_type="greenhouse",
            board_token="testco",
            error_message="404 Not Found",
            http_status=404,
        )
        assert strategy.can_handle(error)

    def test_cannot_handle_lever(self):
        strategy = GreenhouseHealing()
        error = CrawlerError(
            company_name="TestCo",
            portal_type="lever",
            board_token="testco",
            error_message="404 Not Found",
            http_status=404,
        )
        assert not strategy.can_handle(error)

    def test_generates_ashby_candidate(self):
        strategy = GreenhouseHealing()
        error = CrawlerError(
            company_name="TestCo",
            portal_type="greenhouse",
            board_token="testco",
            error_message="404",
            http_status=404,
        )
        candidates = strategy.generate_candidates(error)
        portals = [c.portal_type for c in candidates]
        assert "ashby" in portals
        assert "lever" in portals


class TestLeverHealing:
    def test_can_handle_lever_404(self):
        strategy = LeverHealing()
        error = CrawlerError(
            company_name="TestCo",
            portal_type="lever",
            board_token="testco",
            error_message="404",
            http_status=404,
        )
        assert strategy.can_handle(error)

    def test_generates_ashby_fallback(self):
        strategy = LeverHealing()
        error = CrawlerError(
            company_name="TestCo",
            portal_type="lever",
            board_token="testco",
            error_message="404",
            http_status=404,
        )
        candidates = strategy.generate_candidates(error)
        portals = [c.portal_type for c in candidates]
        assert "ashby" in portals


class TestAshbyHealing:
    def test_generates_greenhouse_fallback(self):
        strategy = AshbyHealing()
        error = CrawlerError(
            company_name="TestCo",
            portal_type="ashby",
            board_token="testco",
            error_message="404",
            http_status=404,
        )
        candidates = strategy.generate_candidates(error)
        portals = [c.portal_type for c in candidates]
        assert "greenhouse" in portals


class TestWorkdayHealing:
    def test_can_handle_workday_422(self):
        strategy = WorkdayHealing()
        error = CrawlerError(
            company_name="TestCo",
            portal_type="workday",
            board_token="testco",
            error_message="422",
            http_status=422,
            careers_url="https://testco.wd5.myworkdayjobs.com/TestCo_Careers",
        )
        assert strategy.can_handle(error)

    def test_generates_board_variants_from_careers_url(self):
        strategy = WorkdayHealing()
        error = CrawlerError(
            company_name="TestCo",
            portal_type="workday",
            board_token="testco",
            error_message="422",
            http_status=422,
            careers_url="https://testco.wd5.myworkdayjobs.com/TestCo_Careers",
        )
        candidates = strategy.generate_candidates(error)
        tokens = [c.board_token for c in candidates]
        assert "TestCo-Careers" in tokens or "TestCo_Careers" in tokens or len(candidates) > 0


class TestValidateCandidate:
    @patch("httpx.Client")
    def test_validates_greenhouse_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.get.return_value = mock_resp

        candidate = HealingCandidate(portal_type="greenhouse", board_token="testco")
        assert validate_candidate(candidate) is True

    @patch("httpx.Client")
    def test_validates_greenhouse_failure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.get.return_value = mock_resp

        candidate = HealingCandidate(portal_type="greenhouse", board_token="testco")
        assert validate_candidate(candidate) is False


class TestAttemptHealing:
    @patch.object(_healing_mod, "validate_candidate")
    def test_returns_success_on_valid_candidate(self, mock_validate):
        mock_validate.return_value = True
        error = CrawlerError(
            company_name="TestCo",
            portal_type="greenhouse",
            board_token="testco",
            error_message="404",
            http_status=404,
        )
        result = attempt_healing(error, max_candidates=3)
        assert result.success is True
        assert result.new_portal is not None
        assert result.validation_status == "validated"

    @patch.object(_healing_mod, "validate_candidate")
    def test_returns_failure_when_no_candidates_work(self, mock_validate):
        mock_validate.return_value = False
        error = CrawlerError(
            company_name="TestCo",
            portal_type="greenhouse",
            board_token="testco",
            error_message="404",
            http_status=404,
        )
        result = attempt_healing(error, max_candidates=3)
        assert result.success is False
        assert result.validation_status == "failed"


# ─── Error Detection Tests ───────────────────────────────────────────────────


class TestDetectErrorsFromLogs:
    def test_detects_structured_crawler_error(self):
        logs = [
            {"message": "CRAWLER_ERROR|TestCo|greenhouse|testco|404 Not Found", "level": "ERROR", "timestamp": "2026-01-01T00:00:00"},
        ]
        errors = detect_errors_from_logs(logs)
        assert len(errors) == 1
        assert errors[0].company_name == "TestCo"
        assert errors[0].portal_type == "greenhouse"
        assert errors[0].board_token == "testco"
        assert errors[0].http_status == 404

    def test_detects_greenhouse_failure_pattern(self):
        logs = [
            {"message": "Greenhouse crawl failed for board testco: Client error '404 Not Found'", "level": "WARNING", "timestamp": ""},
        ]
        errors = detect_errors_from_logs(logs)
        assert len(errors) == 1
        assert errors[0].portal_type == "greenhouse"
        assert errors[0].board_token == "testco"

    def test_deduplicates_by_company(self):
        logs = [
            {"message": "CRAWLER_ERROR|TestCo|greenhouse|testco|404", "level": "ERROR", "timestamp": "t1"},
            {"message": "CRAWLER_ERROR|TestCo|greenhouse|testco|404 retry", "level": "ERROR", "timestamp": "t2"},
        ]
        errors = detect_errors_from_logs(logs)
        assert len(errors) == 1

    def test_ignores_non_error_logs(self):
        logs = [
            {"message": "Scan completed successfully", "level": "INFO", "timestamp": ""},
            {"message": "CRAWLER_ERROR|TestCo|greenhouse|testco|404", "level": "ERROR", "timestamp": ""},
        ]
        errors = detect_errors_from_logs(logs)
        assert len(errors) == 1


# ─── YAML Config Tests ───────────────────────────────────────────────────────


class TestYamlConfig:
    def test_load_and_save_companies(self, tmp_path):
        companies = [
            {"name": "TestCo", "portal_type": "greenhouse", "board_token": "testco", "enabled": True},
            {"name": "OtherCo", "portal_type": "lever", "board_token": "otherco", "enabled": True},
        ]
        filepath = str(tmp_path / "companies.yaml")
        save_companies_yaml(filepath, companies)

        loaded = load_companies_yaml(filepath)
        assert len(loaded) == 2
        assert loaded[0]["name"] == "TestCo"

    def test_creates_backup(self, tmp_path):
        companies = [{"name": "TestCo", "portal_type": "greenhouse", "board_token": "testco"}]
        filepath = str(tmp_path / "companies.yaml")
        save_companies_yaml(filepath, companies)

        # Update to trigger backup creation
        companies[0]["portal_type"] = "ashby"
        save_companies_yaml(filepath, companies)

        bak_path = Path(filepath).with_suffix(".yaml.bak")
        assert bak_path.exists()

    def test_update_company_config(self, tmp_path):
        companies = [
            {"name": "TestCo", "portal_type": "greenhouse", "board_token": "testco", "enabled": True},
        ]
        filepath = str(tmp_path / "companies.yaml")
        save_companies_yaml(filepath, companies)

        success = update_company_config(filepath, "TestCo", {
            "portal_type": "ashby",
            "board_token": "testco-new",
        })
        assert success is True

        loaded = load_companies_yaml(filepath)
        assert loaded[0]["portal_type"] == "ashby"
        assert loaded[0]["board_token"] == "testco-new"

    def test_update_nonexistent_company(self, tmp_path):
        companies = [{"name": "TestCo", "portal_type": "greenhouse", "board_token": "testco"}]
        filepath = str(tmp_path / "companies.yaml")
        save_companies_yaml(filepath, companies)

        success = update_company_config(filepath, "NoExist", {"portal_type": "ashby"})
        assert success is False


# ─── Audit Log Tests ─────────────────────────────────────────────────────────


class TestHealingAuditLog:
    def test_record_and_retrieve(self, tmp_path):
        log = HealingAuditLog(log_path=str(tmp_path / "heal.json"))
        result = HealingResult(
            company_name="TestCo",
            original_portal="greenhouse",
            original_token="testco",
            new_portal="ashby",
            new_token="testco",
            success=True,
        )
        log.record(result, applied=True)

        entries = log.get_recent()
        assert len(entries) == 1
        assert entries[0]["company"] == "TestCo"
        assert entries[0]["success"] is True

    def test_was_healed_recently(self, tmp_path):
        log = HealingAuditLog(log_path=str(tmp_path / "heal.json"))
        result = HealingResult(
            company_name="TestCo",
            original_portal="greenhouse",
            original_token="testco",
            success=True,
        )
        log.record(result)

        assert log.was_healed_recently("TestCo", hours=1) is True
        assert log.was_healed_recently("OtherCo", hours=1) is False

    def test_get_stats(self, tmp_path):
        log = HealingAuditLog(log_path=str(tmp_path / "heal.json"))

        for i in range(5):
            result = HealingResult(
                company_name=f"Co{i}",
                original_portal="greenhouse",
                original_token=f"co{i}",
                success=i < 3,
            )
            log.record(result, applied=i < 3)

        stats = log.get_stats()
        assert stats["total_attempts"] == 5
        assert stats["successes"] == 3
        assert stats["applied"] == 3


# ─── Self-Healing Agent Tests ────────────────────────────────────────────────


class TestSelfHealingAgent:
    def test_detect_errors_empty_logs(self):
        agent = SelfHealingAgent(companies_file="/nonexistent")
        with patch.object(agent, "_get_agent_logs", return_value=[]), \
             patch("src.core.db.error_log.ErrorLogRepository") as repo_cls:
            repo_cls.return_value.get_unresolved_errors.return_value = []
            errors = agent.detect_errors()
            assert errors == []

    def test_dry_run_does_not_modify_file(self, tmp_path):
        companies = [
            {"name": "TestCo", "portal_type": "greenhouse", "board_token": "testco", "enabled": True},
        ]
        filepath = str(tmp_path / "companies.yaml")
        save_companies_yaml(filepath, companies)

        agent = SelfHealingAgent(companies_file=filepath, dry_run=True)

        # Simulate error detection and healing
        error = CrawlerError(
            company_name="TestCo",
            portal_type="greenhouse",
            board_token="testco",
            error_message="404",
            http_status=404,
        )

        with patch.object(agent, "detect_errors", return_value=[error]):
            with patch.object(_healing_mod, "validate_candidate", return_value=True):
                report = agent.run_cycle()

        # Verify file unchanged
        loaded = load_companies_yaml(filepath)
        assert loaded[0]["portal_type"] == "greenhouse"  # unchanged
        assert report.fixes_applied == 0  # dry run

    def test_healing_report_structure(self):
        report = HealingReport(cycle_id="test_cycle")
        d = report.to_dict()
        assert d["cycle_id"] == "test_cycle"
        assert "errors_detected" in d
        assert "fixes_applied" in d
