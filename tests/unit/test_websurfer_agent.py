"""Unit tests for WebSurfer micro-agent rolling buffer and Playwright action dispatcher."""

import importlib
from unittest.mock import AsyncMock, MagicMock
import pytest

_ws_mod = importlib.import_module("src.pipeline.4_submission.websurfer_agent")
WebSurferAgent = _ws_mod.WebSurferAgent

_ad_mod = importlib.import_module("src.pipeline.4_submission.action_dispatcher")
ActionDispatcher = _ad_mod.ActionDispatcher


# ============================================================================
# WebSurferAgent Rolling Buffer Tests (<= 5 Turns)
# ============================================================================

def test_websurfer_rolling_buffer_caps_at_5_turns():
    """Verify rolling memory buffer strictly caps at 5 turns and evicts FIFO."""
    agent = WebSurferAgent(max_buffer_turns=5)

    for turn in range(8):
        agent.record_turn_action(
            turn_idx=turn,
            action={"command": "click", "bid": turn},
            observation=f"Clicked element {turn}",
        )

    assert len(agent.history_buffer) == 5
    # Evicted turns 0, 1, 2. Remaining must be turns 3, 4, 5, 6, 7
    turn_indices = [entry["turn_idx"] for entry in agent.history_buffer]
    assert turn_indices == [3, 4, 5, 6, 7]
    assert agent.history_buffer[0]["turn_idx"] == 3
    assert agent.history_buffer[-1]["turn_idx"] == 7


def test_websurfer_rolling_buffer_custom_capacity_and_clear():
    """Verify customizable buffer limit and clear capability."""
    agent = WebSurferAgent(max_buffer_turns=3)
    agent.record_turn_action(turn_idx=0, action={"command": "type", "bid": 1, "text": "Alice"})
    agent.record_turn_action(turn_idx=1, action={"command": "type", "bid": 2, "text": "Smith"})
    agent.record_turn_action(turn_idx=2, action={"command": "click", "bid": 3})
    agent.record_turn_action(turn_idx=3, action={"command": "stop", "reason": "DONE"})

    assert len(agent.history_buffer) == 3
    assert [e["turn_idx"] for e in agent.history_buffer] == [1, 2, 3]

    agent.clear_history()
    assert len(agent.history_buffer) == 0


# ============================================================================
# WebSurferAgent Structured Command Decision Engine Tests
# ============================================================================

def test_websurfer_decide_action_type_and_click():
    """Verify rule-guided decision engine generates structured type and click commands."""
    agent = WebSurferAgent()
    profile = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane.doe@example.com",
    }

    # First name textbox prompt representation
    prompt_first_name = '[1] <textbox> "Legal First Name"'
    action_1 = agent.decide_action(prompt_first_name, profile)
    assert action_1["command"] == "type"
    assert action_1["bid"] == 1
    assert action_1["text"] == "Jane"

    # Save button click
    prompt_button = '[4] <button> "Save and Continue"'
    action_2 = agent.decide_action(prompt_button, profile)
    assert action_2["command"] == "click"
    assert action_2["bid"] == 4


def test_websurfer_decide_action_select_upload_and_stop():
    """Verify structured select_option, upload_file, and stop commands."""
    agent = WebSurferAgent()
    profile = {
        "country": "United States",
        "resume_path": "/path/to/resume.pdf",
    }

    # Select dropdown
    prompt_select = '[3] <combobox> "Country" (Options: United States, Canada)'
    action_select = agent.decide_action(prompt_select, profile)
    assert action_select["command"] == "select_option"
    assert action_select["bid"] == 3
    assert action_select["value"] == "United States"

    # File upload
    prompt_upload = '[5] <file_upload> "Resume / CV"'
    action_upload = agent.decide_action(prompt_upload, profile)
    assert action_upload["command"] == "upload_file"
    assert action_upload["bid"] == 5
    assert action_upload["file_path"] == "/path/to/resume.pdf"

    # Unrecognized or terminal state triggers stop for HITL
    prompt_hitl = '[99] <heading> "Complex Verification Step"'
    action_stop = agent.decide_action(prompt_hitl, profile)
    assert action_stop["command"] == "stop"
    assert action_stop["reason"] == "READY_FOR_HITL"


def test_websurfer_pluggable_custom_decision_engine():
    """Verify custom decision engine callback is invoked when provided."""
    custom_engine = MagicMock(return_value={"command": "click", "bid": 99, "custom_meta": "ok"})
    agent = WebSurferAgent(decision_engine=custom_engine)

    prompt = '[99] <button> "Custom Trigger"'
    profile = {"first_name": "Bob"}
    decision = agent.decide_action(prompt, profile)

    assert decision["command"] == "click"
    assert decision["bid"] == 99
    assert decision["custom_meta"] == "ok"
    custom_engine.assert_called_once_with(prompt, profile, agent.history_buffer)


# ============================================================================
# ActionDispatcher Playwright Execution Tests (Sync & Async)
# ============================================================================

def test_action_dispatcher_sync_type():
    """Verify ActionDispatcher executes type action using [data-bid='{bid}'] selector on sync page."""
    dispatcher = ActionDispatcher()
    mock_page = MagicMock()
    mock_page.is_visible.return_value = True

    action = {"command": "type", "bid": 1, "text": "Jane"}
    success = dispatcher.execute(action, mock_page)

    assert success is True
    mock_page.fill.assert_called_once_with("[data-bid='1']", "Jane")


def test_action_dispatcher_sync_click():
    """Verify ActionDispatcher executes click action on sync page."""
    dispatcher = ActionDispatcher()
    mock_page = MagicMock()
    mock_page.is_visible.return_value = True

    action = {"command": "click", "bid": 4}
    success = dispatcher.execute(action, mock_page)

    assert success is True
    mock_page.click.assert_called_once_with("[data-bid='4']")


def test_action_dispatcher_sync_select_option():
    """Verify ActionDispatcher executes select_option action on sync page."""
    dispatcher = ActionDispatcher()
    mock_page = MagicMock()
    mock_page.is_visible.return_value = True

    action = {"command": "select_option", "bid": 3, "value": "United States"}
    success = dispatcher.execute(action, mock_page)

    assert success is True
    mock_page.select_option.assert_called_once_with("[data-bid='3']", "United States")


def test_action_dispatcher_sync_upload_file():
    """Verify ActionDispatcher executes upload_file / set_input_files action on sync page."""
    dispatcher = ActionDispatcher()
    mock_page = MagicMock()
    mock_page.is_visible.return_value = True

    action = {"command": "upload_file", "bid": 5, "file_path": "/path/to/resume.pdf"}
    success = dispatcher.execute(action, mock_page)

    assert success is True
    mock_page.set_input_files.assert_called_once_with("[data-bid='5']", "/path/to/resume.pdf")


def test_action_dispatcher_sync_fallback_and_error_handling():
    """Verify ActionDispatcher handles missing bids, unknown commands, and exceptions gracefully."""
    dispatcher = ActionDispatcher()
    mock_page = MagicMock()
    mock_page.is_visible.return_value = False

    # Element not visible
    action = {"command": "click", "bid": 99}
    assert dispatcher.execute(action, mock_page) is False

    # Stop command returns True without touching page
    action_stop = {"command": "stop", "reason": "READY_FOR_HITL"}
    assert dispatcher.execute(action_stop, mock_page) is True

    # Unknown command returns False
    action_unknown = {"command": "teleport", "bid": 1}
    assert dispatcher.execute(action_unknown, mock_page) is False

    # Exception during execution handled safely
    mock_page.is_visible.side_effect = Exception("Page crashed")
    assert dispatcher.execute({"command": "click", "bid": 1}, mock_page) is False


@pytest.mark.asyncio
async def test_action_dispatcher_async_execution():
    """Verify ActionDispatcher supports async Playwright pages seamlessly."""
    dispatcher = ActionDispatcher()
    mock_async_page = AsyncMock()
    mock_async_page.is_visible.return_value = True

    action_type = {"command": "type", "bid": 2, "text": "Doe"}
    res_type = await dispatcher.execute_async(action_type, mock_async_page)
    assert res_type is True
    mock_async_page.fill.assert_awaited_once_with("[data-bid='2']", "Doe")

    action_click = {"command": "click", "bid": 7}
    res_click = await dispatcher.execute_async(action_click, mock_async_page)
    assert res_click is True
    mock_async_page.click.assert_awaited_once_with("[data-bid='7']")
