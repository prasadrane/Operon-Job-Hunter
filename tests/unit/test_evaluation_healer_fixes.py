"""Tests for evaluation_healer.py type safety + narrow except fixes (Task 4)."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_eh_mod = importlib.import_module("src.pipeline.5_lifecycle.healing.evaluation_healer")
EvaluationHealer = _eh_mod.EvaluationHealer


@pytest.fixture
def healer(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("MIN_FIT_SCORE=72.0\n")
    return EvaluationHealer(env_file=str(env))


@pytest.fixture
def healer_no_env(tmp_path: Path):
    return EvaluationHealer(env_file=str(tmp_path / "missing.env"))


def _patch_settings(mock_settings):
    """Patch src.core.config.get_settings inside the evaluation_healer module."""
    mock_mod = MagicMock()
    mock_mod.get_settings = lambda: mock_settings
    return patch.dict("sys.modules", {"src.core.config": mock_mod})


# ── 1. Valid float threshold adjustment ──────────────────────────────────────


class TestAdjustThresholdValidFloat:
    def test_lowers_threshold_by_5_per_3_fallbacks(self, healer):
        mock_settings = SimpleNamespace(min_fit_score=72.0)
        with _patch_settings(mock_settings):
            result = healer._adjust_threshold(fallback_count=6)

        assert result.success is True
        assert result.config_changed is True
        assert result.details["from"] == 72.0
        # 6 // 3 = 2 → 2 * 5 = 10 → 72 - 10 = 62
        assert result.details["to"] == 62.0

    def test_floor_at_50(self, healer):
        mock_settings = SimpleNamespace(min_fit_score=55.0)
        with _patch_settings(mock_settings):
            result = healer._adjust_threshold(fallback_count=30)

        assert result.success is True
        # 30 // 3 = 10 → 10 * 5 = 50 → max(50.0, 55 - 50) = max(50, 5) = 50
        assert result.details["to"] == 50.0

    def test_string_numeric_setting_cast_to_float(self, healer):
        """float() cast handles string-typed settings (e.g. from env)."""
        mock_settings = SimpleNamespace(min_fit_score="80.0")
        with _patch_settings(mock_settings):
            result = healer._adjust_threshold(fallback_count=3)

        assert result.success is True
        assert result.details["from"] == 80.0
        # 3 // 3 = 1 → 1 * 5 = 5 → 80 - 5 = 75
        assert result.details["to"] == 75.0

    def test_no_op_when_already_at_minimum(self, healer):
        mock_settings = SimpleNamespace(min_fit_score=50.0)
        with _patch_settings(mock_settings):
            result = healer._adjust_threshold(fallback_count=3)

        assert result.success is True
        assert result.details["current_threshold"] == 50.0


# ── 2. ValueError / TypeError handled gracefully ────────────────────────────


class TestAdjustThresholdNonNumeric:
    def test_falls_back_to_72_on_value_error(self, healer):
        mock_settings = SimpleNamespace(min_fit_score="not_a_number")
        with _patch_settings(mock_settings):
            result = healer._adjust_threshold(fallback_count=3)

        assert result.success is True
        # Falls back to default 72.0, then 3//3=1 → 72 - 5 = 67
        assert result.details["from"] == 72.0
        assert result.details["to"] == 67.0

    def test_falls_back_to_72_on_type_error(self, healer):
        mock_settings = SimpleNamespace(min_fit_score=None)
        with _patch_settings(mock_settings):
            result = healer._adjust_threshold(fallback_count=3)

        assert result.success is True
        assert result.details["from"] == 72.0

    def test_falls_back_when_settings_raises_oserror(self, healer):
        """If get_settings() itself raises OSError, fallback still works."""
        def _raise():
            raise OSError("config file missing")

        mock_mod = MagicMock()
        mock_mod.get_settings = _raise
        with patch.dict("sys.modules", {"src.core.config": mock_mod}):
            result = healer._adjust_threshold(fallback_count=3)

        assert result.success is True
        assert result.details["from"] == 72.0
        assert result.details["to"] == 67.0


# ── 3. Narrow except catches expected types, lets others propagate ──────────


class TestNarrowExcept:
    def test_oserror_during_env_write_returns_failure(self, healer):
        mock_settings = SimpleNamespace(min_fit_score=72.0)

        def _raise_oserror(*args, **kwargs):
            raise OSError("disk full")

        with _patch_settings(mock_settings):
            with patch.object(Path, "write_text", side_effect=_raise_oserror):
                result = healer._adjust_threshold(fallback_count=3)

        assert result.success is False
        assert "OSError" in result.action

    def test_unexpected_exception_propagates(self, healer):
        """RuntimeError should NOT be caught by narrow except — must propagate."""
        mock_settings = SimpleNamespace(min_fit_score=72.0)

        def _raise_runtime(*args, **kwargs):
            raise RuntimeError("should not be caught")

        with _patch_settings(mock_settings):
            with patch.object(Path, "write_text", side_effect=_raise_runtime):
                with pytest.raises(RuntimeError, match="should not be caught"):
                    healer._adjust_threshold(fallback_count=3)

    def test_valueerror_during_env_write_returns_failure(self, healer):
        mock_settings = SimpleNamespace(min_fit_score=72.0)

        def _raise_valueerror(*args, **kwargs):
            raise ValueError("bad value")

        with _patch_settings(mock_settings):
            with patch.object(Path, "write_text", side_effect=_raise_valueerror):
                result = healer._adjust_threshold(fallback_count=3)

        assert result.success is False
        assert "ValueError" in result.action

    def test_typeerror_during_env_write_returns_failure(self, healer):
        mock_settings = SimpleNamespace(min_fit_score=72.0)

        def _raise_typeerror(*args, **kwargs):
            raise TypeError("bad type")

        with _patch_settings(mock_settings):
            with patch.object(Path, "write_text", side_effect=_raise_typeerror):
                result = healer._adjust_threshold(fallback_count=3)

        assert result.success is False
        assert "TypeError" in result.action


# ── 4. Integration: heal() triggers _adjust_threshold ───────────────────────


class TestHealIntegration:
    def test_heal_triggers_threshold_adjust_after_3_fallbacks(self, healer):
        mock_settings = SimpleNamespace(min_fit_score=72.0)
        errors = [
            SimpleNamespace(error_type="LLM_FALLBACK", id="e1"),
            SimpleNamespace(error_type="LLM_FALLBACK", id="e2"),
            SimpleNamespace(error_type="LLM_FALLBACK", id="e3"),
        ]

        with _patch_settings(mock_settings):
            results = healer.heal(errors)

        threshold_results = [
            r for r in results
            if "min_fit_score" in r.action.lower() or "threshold" in r.action.lower()
        ]
        assert len(threshold_results) >= 1
        assert any(r.success for r in threshold_results)
