"""Unit tests for WizardStateManager: State snapshots, resumption, and TTL expiration."""

import importlib
import os
import time
import pytest

wizard_mod = importlib.import_module("src.pipeline.4_submission.wizard_state_manager")
WizardStateManager = wizard_mod.WizardStateManager
WizardStepState = wizard_mod.WizardStepState


def test_wizard_state_save_and_resume(tmp_path):
    """Verify wizard manager saves step checkpoints and can restore session state."""
    sessions_dir = tmp_path / "wizard_sessions"
    manager = WizardStateManager(sessions_dir=str(sessions_dir))

    session_id = "sess_workday_12345"
    step1_state = WizardStepState(
        step_index=1,
        step_name="My Information",
        fields_filled={"first_name": "Alex", "last_name": "Rivera", "email": "alex.rivera@example.com"},
        dom_hash="hash_step_1_abc",
    )

    manager.save_checkpoint(session_id, step1_state)
    assert manager.has_active_session(session_id) is True

    # Restore checkpoint
    restored = manager.get_latest_checkpoint(session_id)
    assert restored is not None
    assert restored.step_index == 1
    assert restored.step_name == "My Information"
    assert restored.fields_filled["first_name"] == "Alex"


def test_wizard_state_advancement(tmp_path):
    """Verify manager tracks multi-step advancement in sequence."""
    sessions_dir = tmp_path / "wizard_sessions"
    manager = WizardStateManager(sessions_dir=str(sessions_dir))

    session_id = "sess_workday_999"
    manager.save_checkpoint(session_id, WizardStepState(step_index=1, step_name="Info", fields_filled={"name": "Alex"}))
    manager.save_checkpoint(session_id, WizardStepState(step_index=2, step_name="Experience", fields_filled={"company": "Rocket"}))
    manager.save_checkpoint(session_id, WizardStepState(step_index=3, step_name="Voluntary Disclosures", fields_filled={"gender": "Decline"}))

    latest = manager.get_latest_checkpoint(session_id)
    assert latest.step_index == 3
    assert latest.step_name == "Voluntary Disclosures"
    assert len(manager.get_all_steps(session_id)) == 3


def test_wizard_session_ttl_expiration(tmp_path):
    """Verify expired sessions beyond TTL are purged and not resumed."""
    sessions_dir = tmp_path / "wizard_sessions"
    manager = WizardStateManager(sessions_dir=str(sessions_dir), ttl_seconds=1)

    session_id = "sess_expired_001"
    manager.save_checkpoint(session_id, WizardStepState(step_index=1, step_name="Start", fields_filled={}))
    assert manager.has_active_session(session_id) is True

    time.sleep(1.2)
    assert manager.has_active_session(session_id) is False
    assert manager.get_latest_checkpoint(session_id) is None


def test_wizard_session_cleanup(tmp_path):
    """Verify manual session clearing after final successful submission."""
    sessions_dir = tmp_path / "wizard_sessions"
    manager = WizardStateManager(sessions_dir=str(sessions_dir))

    session_id = "sess_complete_777"
    manager.save_checkpoint(session_id, WizardStepState(step_index=1, step_name="Start", fields_filled={}))
    assert manager.has_active_session(session_id) is True

    manager.clear_session(session_id)
    assert manager.has_active_session(session_id) is False
