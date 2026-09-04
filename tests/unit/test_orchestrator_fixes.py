"""Tests for HealingOrchestrator._mark_resolved portal_type fix.

Task-2 contract: verify that _mark_resolved extracts portal_type from
result.details["from"]["portal_type"] and passes it to
repo.mark_company_resolved; falls back to no portal_type when details
are missing.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

_orch_mod = importlib.import_module("src.pipeline.5_lifecycle.healing.orchestrator")
_base_mod = importlib.import_module("src.pipeline.5_lifecycle.healing.base")
HealingReport = _base_mod.HealingReport
HealingResult = _base_mod.HealingResult
HealingOrchestrator = _orch_mod.HealingOrchestrator


@dataclass
class _FakeRepo:
    """Tracks calls to mark_company_resolved / mark_resolved."""
    company_calls: List[Dict[str, Any]] = field(default_factory=list)
    id_calls: List[str] = field(default_factory=list)

    def mark_resolved(self, error_id: str) -> None:
        self.id_calls.append(error_id)

    def mark_company_resolved(self, company: str, portal_type: Optional[str] = None) -> int:
        self.company_calls.append({"company": company, "portal_type": portal_type})
        return 1


def _result_with_portal(portal_type: Optional[str], **overrides) -> HealingResult:
    details: Dict[str, Any] = {}
    if portal_type is not None:
        details = {"from": {"portal_type": portal_type}}
    return HealingResult(
        healer="discovery",
        action="fix config",
        success=True,
        company="TestCo",
        details=details,
        **overrides,
    )


class TestMarkResolvedPortalType:
    def test_portal_type_extracted_and_passed(self):
        orch = HealingOrchestrator()
        repo = _FakeRepo()
        report = HealingReport(
            healer="discovery",
            fixes_applied=1,
            results=[_result_with_portal("greenhouse")],
        )
        orch._mark_resolved(repo, report)
        assert repo.company_calls == [{"company": "TestCo", "portal_type": "greenhouse"}]

    def test_portal_type_ashby(self):
        orch = HealingOrchestrator()
        repo = _FakeRepo()
        report = HealingReport(
            healer="discovery",
            fixes_applied=1,
            results=[_result_with_portal("ashby")],
        )
        orch._mark_resolved(repo, report)
        assert repo.company_calls == [{"company": "TestCo", "portal_type": "ashby"}]

    def test_fallback_no_details(self):
        orch = HealingOrchestrator()
        repo = _FakeRepo()
        # details={} — no "from" key
        report = HealingReport(
            healer="discovery",
            fixes_applied=1,
            results=[_result_with_portal(None)],
        )
        orch._mark_resolved(repo, report)
        assert repo.company_calls == [{"company": "TestCo", "portal_type": None}]

    def test_fallback_details_none(self):
        orch = HealingOrchestrator()
        repo = _FakeRepo()
        result = HealingResult(
            healer="discovery", action="fix", success=True,
            company="TestCo", details=None,  # type: ignore[arg-type]
        )
        report = HealingReport(healer="discovery", fixes_applied=1, results=[result])
        orch._mark_resolved(repo, report)
        assert repo.company_calls == [{"company": "TestCo", "portal_type": None}]

    def test_error_id_path_unaffected(self):
        orch = HealingOrchestrator()
        repo = _FakeRepo()
        result = HealingResult(
            healer="discovery", action="fix", success=True,
            error_id="err-123", company="TestCo",
            details={"from": {"portal_type": "lever"}},
        )
        report = HealingReport(healer="discovery", fixes_applied=1, results=[result])
        orch._mark_resolved(repo, report)
        # error_id takes precedence (per code); company path not taken
        assert repo.id_calls == ["err-123"]
        assert repo.company_calls == []

    def test_failed_result_ignored(self):
        orch = HealingOrchestrator()
        repo = _FakeRepo()
        result = HealingResult(
            healer="discovery", action="fix", success=False,
            company="TestCo", details={"from": {"portal_type": "greenhouse"}},
        )
        report = HealingReport(healer="discovery", fixes_applied=0, results=[result])
        orch._mark_resolved(repo, report)
        assert repo.company_calls == []
        assert repo.id_calls == []

    def test_multiple_results_mixed(self):
        orch = HealingOrchestrator()
        repo = _FakeRepo()
        report = HealingReport(
            healer="discovery",
            fixes_applied=3,
            results=[
                _result_with_portal("greenhouse"),
                _result_with_portal(None),  # fallback
                HealingResult(
                    healer="discovery", action="fix", success=True,
                    error_id="e-1", company="OtherCo",
                    details={"from": {"portal_type": "workday"}},
                ),
            ],
        )
        orch._mark_resolved(repo, report)
        assert repo.company_calls == [
            {"company": "TestCo", "portal_type": "greenhouse"},
            {"company": "TestCo", "portal_type": None},
        ]
        assert repo.id_calls == ["e-1"]

    def test_malformed_details_no_crash(self):
        orch = HealingOrchestrator()
        repo = _FakeRepo()
        # "from" is a string, not a dict — should not crash
        result = HealingResult(
            healer="discovery", action="fix", success=True,
            company="TestCo", details={"from": "not-a-dict"},
        )
        report = HealingReport(healer="discovery", fixes_applied=1, results=[result])
        orch._mark_resolved(repo, report)
        assert repo.company_calls == [{"company": "TestCo", "portal_type": None}]
