"""Unit tests for modular ActionDispatcher handlers (Click, Type, Select, Upload)."""

import importlib
from unittest.mock import AsyncMock, MagicMock
import pytest

_disp_mod = importlib.import_module("src.pipeline.4_submission.action_dispatcher")
ActionDispatcher = getattr(_disp_mod, "ActionDispatcher")

_hand_mod = importlib.import_module("src.pipeline.4_submission.handlers")
TypeActionHandler = getattr(_hand_mod, "TypeActionHandler")
ClickActionHandler = getattr(_hand_mod, "ClickActionHandler")
SelectActionHandler = getattr(_hand_mod, "SelectActionHandler")
UploadActionHandler = getattr(_hand_mod, "UploadActionHandler")


def test_type_action_handler_sync_and_async():
    """Verify TypeActionHandler fills text into selector."""
    handler = TypeActionHandler()
    mock_page = MagicMock()

    res = handler.execute("[data-bid='10']", {"text": "Alex Rivera"}, mock_page)
    assert res is True
    mock_page.fill.assert_called_once_with("[data-bid='10']", "Alex Rivera")


@pytest.mark.asyncio
async def test_type_action_handler_async():
    handler = TypeActionHandler()
    mock_page = AsyncMock()

    res = await handler.execute_async("[data-bid='10']", {"text": "Alex Rivera"}, mock_page)
    assert res is True
    mock_page.fill.assert_awaited_once_with("[data-bid='10']", "Alex Rivera")


def test_click_action_handler():
    """Verify ClickActionHandler clicks target selector."""
    handler = ClickActionHandler()
    mock_page = MagicMock()

    res = handler.execute("[data-bid='42']", {}, mock_page)
    assert res is True
    mock_page.click.assert_called_once_with("[data-bid='42']")


def test_select_action_handler():
    """Verify SelectActionHandler selects dropdown option."""
    handler = SelectActionHandler()
    mock_page = MagicMock()

    res = handler.execute("[data-bid='15']", {"value": "Full-Time"}, mock_page)
    assert res is True
    mock_page.select_option.assert_called_once_with("[data-bid='15']", "Full-Time")


def test_upload_action_handler():
    """Verify UploadActionHandler sets input files."""
    handler = UploadActionHandler()
    mock_page = MagicMock()

    res = handler.execute("[data-bid='99']", {"file_path": "data/artifacts/resume.pdf"}, mock_page)
    assert res is True
    mock_page.set_input_files.assert_called_once_with("[data-bid='99']", "data/artifacts/resume.pdf")


def test_action_dispatcher_delegation_to_handlers():
    """Verify ActionDispatcher delegates to modular handlers seamlessly."""
    dispatcher = ActionDispatcher()
    mock_page = MagicMock()
    mock_page.is_visible.return_value = True

    # Type action
    assert dispatcher.execute({"command": "type", "bid": "1", "text": "Chicago"}, mock_page) is True
    # Click action
    assert dispatcher.execute({"command": "click", "bid": "2"}, mock_page) is True
    # Select action
    assert dispatcher.execute({"command": "select", "bid": "3", "value": "Yes"}, mock_page) is True
    # Upload action
    assert dispatcher.execute({"command": "upload_file", "bid": "4", "file_path": "resume.pdf"}, mock_page) is True
    # Stop command
    assert dispatcher.execute({"command": "stop", "reason": "done"}, mock_page) is True
