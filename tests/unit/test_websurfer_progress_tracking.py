"""Unit tests for WebSurferAgent stateful input progress tracking and sequential form traversal."""

import importlib
import pytest

_ws_mod = importlib.import_module("src.pipeline.4_submission.websurfer_agent")
WebSurferAgent = _ws_mod.WebSurferAgent


def test_websurfer_advances_sequentially_without_looping_first_textbox():
    """Verify WebSurferAgent does not repeatedly select the first textbox when multiple fields exist."""
    agent = WebSurferAgent()
    profile = {
        "first_name": "Alex",
        "last_name": "Rivera",
        "email": "alex.rivera@example.com",
        "phone": "555-0199",
        "resume_pdf_path": "data/artifacts/resume.pdf",
    }
    prompt_view = (
        '[1] <textbox> "First Name"\n'
        '[2] <textbox> "Last Name"\n'
        '[3] <textbox> "Email Address"\n'
        '[4] <textbox> "Phone Number"\n'
        '[5] <file_upload> "Upload Resume (PDF/DOCX)"\n'
        '[6] <button> "Submit Application"\n'
    )

    # Step 1: Should target First Name [1]
    action1 = agent.decide_action(prompt_view, profile)
    assert action1 == {"command": "type", "bid": 1, "text": "Alex"}
    agent.record_turn_action(1, action1, observation="Typed Alex into First Name")

    # Step 2: Should advance to Last Name [2], NOT loop back to First Name [1]
    action2 = agent.decide_action(prompt_view, profile)
    assert action2 == {"command": "type", "bid": 2, "text": "Rivera"}
    agent.record_turn_action(2, action2, observation="Typed Rivera into Last Name")

    # Step 3: Should advance to Email [3]
    action3 = agent.decide_action(prompt_view, profile)
    assert action3 == {"command": "type", "bid": 3, "text": "alex.rivera@example.com"}
    agent.record_turn_action(3, action3, observation="Typed email")

    # Step 4: Should advance to Phone [4]
    action4 = agent.decide_action(prompt_view, profile)
    assert action4 == {"command": "type", "bid": 4, "text": "555-0199"}
    agent.record_turn_action(4, action4, observation="Typed phone")

    # Step 5: Should advance to Resume Upload [5]
    action5 = agent.decide_action(prompt_view, profile)
    assert action5 == {"command": "upload_file", "bid": 5, "file_path": "data/artifacts/resume.pdf"}
    agent.record_turn_action(5, action5, observation="Uploaded resume")

    # Step 6: Should click Submit button [6]
    action6 = agent.decide_action(prompt_view, profile)
    assert action6 == {"command": "click", "bid": 6}
    agent.record_turn_action(6, action6, observation="Clicked submit")

    # Step 7: After submit button is clicked, next action should stop / be ready for HITL
    action7 = agent.decide_action(prompt_view, profile)
    assert action7["command"] == "stop"


def test_websurfer_clear_history_resets_completed_tracking():
    """Verify clear_history resets completed fields tracking."""
    agent = WebSurferAgent()
    profile = {"first_name": "Alex"}
    prompt_view = '[1] <textbox> "First Name"\n'

    action1 = agent.decide_action(prompt_view, profile)
    assert action1 == {"command": "type", "bid": 1, "text": "Alex"}
    agent.record_turn_action(1, action1)

    # Subsequent call stops since bid 1 is completed
    assert agent.decide_action(prompt_view, profile)["command"] == "stop"

    # Clearing history allows re-filling
    agent.clear_history()
    assert agent.decide_action(prompt_view, profile) == {"command": "type", "bid": 1, "text": "Alex"}
