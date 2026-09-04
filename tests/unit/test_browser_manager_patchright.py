"""Tests for Patchright-migrated BrowserManager.

Validates that:
1. BrowserManager creates context via patchright (not playwright)
2. Context has stealth properties (no STEALTH_INIT_SCRIPT, no playwright_stealth)
3. Context launches in headless mode
4. Context launches in headed mode
5. Stale lock cleanup still works
6. Backward compatible with existing submitter_engine usage (duck-typed Playwright)
"""

import importlib
import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(tmp_path, headless=True, **kwargs):
    """Create a BrowserManager with a temp user_data_dir."""
    bm_mod = importlib.import_module("src.pipeline.4_submission.browser_manager")
    return bm_mod.BrowserManager(
        user_data_dir=str(tmp_path / "profile"),
        headless=headless,
        **kwargs,
    )


def _mock_playwright():
    """Return a mock Playwright object with chromium.launch_persistent_context."""
    pw = MagicMock()
    ctx = MagicMock()
    pw.chromium.launch_persistent_context.return_value = ctx
    return pw, ctx


# ---------------------------------------------------------------------------
# 1. BrowserManager creates context with patchright
# ---------------------------------------------------------------------------

def test_create_context_uses_patchright_import(tmp_path):
    """browser_manager module imports from patchright, not playwright."""
    bm_mod = importlib.import_module("src.pipeline.4_submission.browser_manager")
    source_file = bm_mod.__file__
    with open(source_file, "r", encoding="utf-8") as f:
        source = f.read()

    assert "from patchright.sync_api import" in source, (
        "browser_manager must import from patchright.sync_api"
    )
    assert "from playwright.sync_api import" not in source, (
        "browser_manager must NOT import from playwright.sync_api"
    )


def test_create_context_returns_context(tmp_path):
    """create_context(playwright) returns the BrowserContext from launch_persistent_context."""
    manager = _make_manager(tmp_path)
    pw, mock_ctx = _mock_playwright()

    result = manager.create_context(pw)

    assert result is mock_ctx
    pw.chromium.launch_persistent_context.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Context has stealth properties (no manual stealth scripts)
# ---------------------------------------------------------------------------

def test_no_stealth_init_script(tmp_path):
    """STEALTH_INIT_SCRIPT constant must be removed — Patchright handles stealth natively."""
    bm_mod = importlib.import_module("src.pipeline.4_submission.browser_manager")
    assert not hasattr(bm_mod, "STEALTH_INIT_SCRIPT"), (
        "STEALTH_INIT_SCRIPT should be removed; Patchright has built-in stealth"
    )


def test_no_add_init_script_call(tmp_path):
    """create_context must NOT call context.add_init_script (Patchright handles it)."""
    manager = _make_manager(tmp_path)
    pw, mock_ctx = _mock_playwright()

    manager.create_context(pw)

    mock_ctx.add_init_script.assert_not_called()


def test_no_playwright_stealth_import(tmp_path):
    """create_context must NOT attempt to import playwright_stealth."""
    manager = _make_manager(tmp_path)
    pw, mock_ctx = _mock_playwright()

    with patch("builtins.__import__", wraps=__import__) as mock_import:
        manager.create_context(pw)

    for call_args in mock_import.call_args_list:
        imported_name = call_args[0][0]
        assert "playwright_stealth" not in imported_name, (
            "browser_manager must not import playwright_stealth"
        )


# ---------------------------------------------------------------------------
# 3. Context launches successfully in headless mode
# ---------------------------------------------------------------------------

def test_launch_headless(tmp_path):
    """headless=True passes headless=True to launch_persistent_context."""
    manager = _make_manager(tmp_path, headless=True)
    pw, mock_ctx = _mock_playwright()

    manager.create_context(pw)

    call_kwargs = pw.chromium.launch_persistent_context.call_args.kwargs
    assert call_kwargs["headless"] is True


# ---------------------------------------------------------------------------
# 4. Context launches successfully in headed mode
# ---------------------------------------------------------------------------

def test_launch_headed(tmp_path):
    """headless=False passes headless=False to launch_persistent_context."""
    manager = _make_manager(tmp_path, headless=False)
    pw, mock_ctx = _mock_playwright()

    manager.create_context(pw)

    call_kwargs = pw.chromium.launch_persistent_context.call_args.kwargs
    assert call_kwargs["headless"] is False


# ---------------------------------------------------------------------------
# 5. Stale lock cleanup still works
# ---------------------------------------------------------------------------

def test_stale_lock_cleanup(tmp_path):
    """_clean_stale_locks removes SingletonLock, SingletonSocket, lockfile but keeps normal files."""
    profile_dir = tmp_path / "lock_profile"
    profile_dir.mkdir()
    lock1 = profile_dir / "SingletonLock"
    lock2 = profile_dir / "SingletonSocket"
    lock3 = profile_dir / "lockfile"
    normal = profile_dir / "Cookies"

    lock1.write_text("lock")
    lock2.write_text("socket")
    lock3.write_text("lockfile")
    normal.write_text("data")

    bm_mod = importlib.import_module("src.pipeline.4_submission.browser_manager")
    manager = bm_mod.BrowserManager(user_data_dir=str(profile_dir), headless=True)
    manager._clean_stale_locks()

    assert not lock1.exists()
    assert not lock2.exists()
    assert not lock3.exists()
    assert normal.exists()


def test_stale_lock_cleanup_called_before_launch(tmp_path):
    """create_context calls _clean_stale_locks before launching."""
    manager = _make_manager(tmp_path)
    pw, _ = _mock_playwright()

    with patch.object(manager, "_clean_stale_locks", wraps=manager._clean_stale_locks) as spy:
        manager.create_context(pw)

    assert spy.call_count >= 1


# ---------------------------------------------------------------------------
# 6. Backward compatible with existing submitter_engine usage
# ---------------------------------------------------------------------------

def test_backward_compatible_create_context_signature(tmp_path):
    """create_context accepts a duck-typed Playwright object (mock or real)."""
    manager = _make_manager(tmp_path)
    # Simulate the exact call pattern from submitter_engine:
    #   with sync_playwright() as playwright:
    #       context = self.browser_manager.create_context(playwright)
    mock_playwright = MagicMock()
    mock_context = MagicMock()
    mock_playwright.chromium.launch_persistent_context.return_value = mock_context

    result = manager.create_context(mock_playwright)

    assert result is mock_context


def test_backward_compatible_launch_args(tmp_path):
    """Launch args still include anti-detection flags that submitter_engine relies on."""
    manager = _make_manager(tmp_path)
    pw, _ = _mock_playwright()

    manager.create_context(pw)

    call_kwargs = pw.chromium.launch_persistent_context.call_args.kwargs
    args = call_kwargs["args"]
    assert "--disable-blink-features=AutomationControlled" in args
    assert "--no-sandbox" in args
    assert call_kwargs["user_data_dir"] == manager.user_data_dir
    assert call_kwargs["viewport"] == manager.viewport
    assert call_kwargs["user_agent"] == manager.user_agent
