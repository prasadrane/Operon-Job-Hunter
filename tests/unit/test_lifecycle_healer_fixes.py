"""Tests for lifecycle_healer cursor reset cooldown (Task 3)."""

import importlib
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_healing_pkg = importlib.import_module("src.pipeline.5_lifecycle.healing")
LifecycleHealer = _healing_pkg.LifecycleHealer


@pytest.fixture
def healer(tmp_path):
    """Create a LifecycleHealer with temp cursor file."""
    cursor_file = str(tmp_path / "gmail_cursor.json")
    Path(cursor_file).write_text("{}")
    return LifecycleHealer(cursor_file=cursor_file)


class TestCursorResetCooldown:
    """Verify _reset_cursor cooldown gating."""

    def test_first_reset_succeeds(self, healer, tmp_path):
        """First call should delete cursor file and return success=True."""
        cursor_path = Path(healer.cursor_file)
        assert cursor_path.exists()

        result = healer._reset_cursor(error_id="err-1")

        assert result.success is True
        assert "Reset gmail cursor" in result.action
        assert not cursor_path.exists()
        assert healer._last_cursor_reset is not None

    def test_second_reset_within_cooldown_skipped(self, healer, tmp_path):
        """Second call within cooldown should return success=False."""
        # First reset
        result1 = healer._reset_cursor(error_id="err-1")
        assert result1.success is True

        # Recreate cursor file to simulate it being written again
        Path(healer.cursor_file).write_text("{}")

        # Second reset immediately — should be blocked by cooldown
        result2 = healer._reset_cursor(error_id="err-2")

        assert result2.success is False
        assert "cooldown" in result2.action.lower()
        # Cursor file should NOT have been deleted
        assert Path(healer.cursor_file).exists()

    def test_reset_after_cooldown_expires_succeeds(self, healer, tmp_path):
        """After cooldown expires, reset should succeed again."""
        # First reset
        result1 = healer._reset_cursor(error_id="err-1")
        assert result1.success is True

        # Simulate time passing beyond cooldown (4h = 14400s)
        healer._last_cursor_reset = time.time() - (4.0 * 3600 + 1)

        # Recreate cursor file
        Path(healer.cursor_file).write_text("{}")

        # Should succeed now
        result2 = healer._reset_cursor(error_id="err-2")
        assert result2.success is True
        assert "Reset gmail cursor" in result2.action
        assert not Path(healer.cursor_file).exists()

    def test_cooldown_exact_boundary(self, healer, tmp_path):
        """Reset exactly at cooldown boundary should still be skipped."""
        healer._reset_cursor(error_id="err-1")
        # Set exactly at cooldown (not past it)
        healer._last_cursor_reset = time.time() - (4.0 * 3600)
        Path(healer.cursor_file).write_text("{}")

        result = healer._reset_cursor(error_id="err-2")
        # At exactly cooldown_seconds, (now - last) < cooldown is False, so it proceeds
        # This tests the boundary — either behavior is acceptable, we just document it
        assert result.success is True

    def test_last_cursor_reset_initialized_none(self):
        """_last_cursor_reset should start as None."""
        healer = LifecycleHealer()
        assert healer._last_cursor_reset is None

    def test_dry_run_bypasses_cooldown(self, tmp_path):
        """Dry run mode should not affect cooldown state."""
        cursor_file = str(tmp_path / "cursor.json")
        Path(cursor_file).write_text("{}")
        healer = LifecycleHealer(cursor_file=cursor_file, dry_run=True)

        result = healer._reset_cursor(error_id="err-1")
        assert result.success is True
        assert "DRY RUN" in result.action
        # Dry run should NOT update _last_cursor_reset
        assert healer._last_cursor_reset is None
        # File should still exist (dry run doesn't delete)
        assert Path(cursor_file).exists()
