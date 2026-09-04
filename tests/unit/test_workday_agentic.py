"""Unit tests for WorkdayAgenticSubmitter multi-step wizard, step transition verification, and error detection."""

import hashlib
import importlib
from unittest.mock import MagicMock, call
import pytest

_wd_mod = importlib.import_module("src.pipeline.4_submission.adapters.workday_agentic")
WorkdayAgenticSubmitter = _wd_mod.WorkdayAgenticSubmitter

_ws_mod = importlib.import_module("src.pipeline.4_submission.websurfer_agent")
WebSurferAgent = _ws_mod.WebSurferAgent

_ch_mod = importlib.import_module("src.pipeline.4_submission.captcha_handler")
CaptchaHandler = _ch_mod.CaptchaHandler


# ============================================================================
# Multi-step Stepping and Max Steps Capping Tests
# ============================================================================

def test_workday_agentic_stepper_caps_at_max_steps():
    """Verify stepper executes up to max_steps when no terminal condition is reached."""
    submitter = WorkdayAgenticSubmitter(max_steps=4)
    mock_page = MagicMock()
    
    # Page never displays review/submit button and save button is always visible
    def mock_is_visible(selector):
        if "Save and Continue" in selector or "bottom-navigation-next-button" in selector:
            return True
        if "Submit" in selector:
            return False
        return False

    mock_page.is_visible.side_effect = mock_is_visible
    # Page state changes each step to avoid stuck transition detection
    state_counter = [0]
    def mock_content():
        state_counter[0] += 1
        return f"<html><body><div id='step_{state_counter[0]}'>Step Content {state_counter[0]}</div></body></html>"

    mock_page.content.side_effect = mock_content
    mock_page.locator.return_value.count.return_value = 0

    preview = submitter.fill_and_navigate(mock_page, {"first_name": "Jane", "last_name": "Doe"})
    assert preview["steps_completed"] == 4
    assert preview["status"] == "MAX_STEPS_REACHED"


def test_workday_agentic_reaches_review_ready_for_hitl():
    """Verify when review/submit page is reached, stepper stops and returns READY_FOR_HITL."""
    submitter = WorkdayAgenticSubmitter(max_steps=6)
    mock_page = MagicMock()

    step_counter = [0]
    def mock_is_visible(selector):
        if "Submit Application" in selector or "bottom-navigation-submit-button" in selector:
            # Become visible on step 3
            return step_counter[0] >= 3
        if "Save and Continue" in selector or "bottom-navigation-next-button" in selector:
            return step_counter[0] < 3
        return False

    def mock_click(selector, **kwargs):
        step_counter[0] += 1

    mock_page.is_visible.side_effect = mock_is_visible
    mock_page.click.side_effect = mock_click
    mock_page.content.side_effect = lambda: f"<html>Step {step_counter[0]}</html>"
    mock_page.locator.return_value.count.return_value = 0

    preview = submitter.fill_and_navigate(mock_page, {"first_name": "Jane", "last_name": "Doe"})
    assert preview["status"] == "READY_FOR_HITL"
    assert preview["steps_completed"] >= 1


# ============================================================================
# Step Transition Verification Tests
# ============================================================================

def test_workday_agentic_detects_failed_step_transition_due_to_validation():
    """Verify stepper detects when clicking next fails to advance DOM state and surfaces validation error."""
    submitter = WorkdayAgenticSubmitter(max_steps=5)
    mock_page = MagicMock()

    # Content doesn't change after clicking next (stuck on same step)
    mock_page.content.return_value = "<html><div class='form'>Unchanged Form</div></html>"

    # Next button is visible
    def mock_is_visible(selector):
        if "Save and Continue" in selector or "bottom-navigation-next-button" in selector:
            return True
        if "Submit" in selector:
            return False
        return False

    mock_page.is_visible.side_effect = mock_is_visible

    # Error element present
    error_elem = MagicMock()
    error_elem.inner_text.return_value = "This field is required."
    error_elem.get_attribute.return_value = "true"

    def mock_locator(selector):
        loc = MagicMock()
        if "aria-invalid" in selector or "css-error" in selector:
            loc.count.return_value = 1
            loc.all.return_value = [error_elem]
            loc.first.is_visible.return_value = True
            loc.first.inner_text.return_value = "This field is required."
        else:
            loc.count.return_value = 0
            loc.all.return_value = []
        return loc

    mock_page.locator.side_effect = mock_locator

    result = submitter.fill_and_navigate(mock_page, {"first_name": "Jane"})
    assert result["status"] in ["VALIDATION_ERROR", "READY_FOR_HITL"]
    assert len(result["errors"]) > 0
    assert any("required" in err.lower() or "invalid" in err.lower() for err in result["errors"])


# ============================================================================
# Error Element Scanning Tests ([aria-invalid='true'], .css-error, role=alert)
# ============================================================================

def test_workday_agentic_scans_aria_invalid_and_css_error():
    """Verify scan_errors inspects aria-invalid, css-error, and error banners."""
    submitter = WorkdayAgenticSubmitter()
    mock_page = MagicMock()

    err_banner = MagicMock()
    err_banner.inner_text.return_value = "Please fix the 2 errors below."
    err_banner.is_visible.return_value = True

    invalid_input = MagicMock()
    invalid_input.get_attribute.side_effect = lambda attr: "Postal Code" if attr == "aria-label" else "true"
    invalid_input.inner_text.return_value = ""
    invalid_input.is_visible.return_value = True

    def mock_locator(selector):
        loc = MagicMock()
        if "error-banner" in selector or ".css-error" in selector:
            loc.count.return_value = 1
            loc.all.return_value = [err_banner]
        elif "aria-invalid" in selector:
            loc.count.return_value = 1
            loc.all.return_value = [invalid_input]
        else:
            loc.count.return_value = 0
            loc.all.return_value = []
        return loc

    mock_page.locator.side_effect = mock_locator

    errors = submitter.scan_errors(mock_page)
    assert len(errors) >= 1
    assert any("Please fix" in e or "Postal Code" in e or "aria-invalid" in e for e in errors)


# ============================================================================
# CAPTCHA Detection and HITL Escalation Tests
# ============================================================================

def test_workday_agentic_detects_captcha_and_escalates():
    """Verify CAPTCHA detection triggers CAPTCHA_DETECTED status immediately."""
    mock_captcha_handler = MagicMock(spec=CaptchaHandler)
    mock_captcha_handler.detect_captcha.return_value = True

    submitter = WorkdayAgenticSubmitter(captcha_handler=mock_captcha_handler)
    mock_page = MagicMock()

    result = submitter.fill_and_navigate(mock_page, {"first_name": "Jane"})
    assert result["status"] == "CAPTCHA_DETECTED"
    assert result["steps_completed"] == 0


# ============================================================================
# Candidate Account Handling Tests
# ============================================================================

def test_workday_agentic_handles_candidate_account_login():
    """Verify handle_account fills email/password and clicks sign-in button when login modal/page is active."""
    submitter = WorkdayAgenticSubmitter()
    mock_page = MagicMock()

    email_loc = MagicMock()
    email_loc.count.return_value = 1
    email_loc.first.is_visible.return_value = True

    pwd_loc = MagicMock()
    pwd_loc.count.return_value = 1
    pwd_loc.first.is_visible.return_value = True

    def mock_locator(selector):
        loc = MagicMock()
        if "email" in selector:
            return email_loc
        elif "password" in selector:
            return pwd_loc
        loc.count.return_value = 0
        return loc

    mock_page.locator.side_effect = mock_locator
    mock_page.is_visible.side_effect = lambda sel: "Sign In" in sel or "signInSubmitButton" in sel

    profile = {"email": "candidate@example.com", "password": "SecurePassword123!"}
    handled = submitter.handle_account(mock_page, profile)
    assert handled is True
    email_loc.first.fill.assert_called_once_with("candidate@example.com")
    pwd_loc.first.fill.assert_called_once_with("SecurePassword123!")


# ============================================================================
# Full Submission Trigger Tests
# ============================================================================

def test_workday_agentic_submit_action():
    """Verify submit() triggers Workday final submit button and verifies receipt."""
    submitter = WorkdayAgenticSubmitter()
    mock_page = MagicMock()

    submit_btn = MagicMock()
    submit_btn.count.return_value = 1
    submit_btn.first.is_visible.return_value = True

    mock_page.locator.return_value = submit_btn
    mock_page.content.return_value = "<html>Thank you for applying! Application ID: WD-987654</html>"

    success, conf_id = submitter.submit(mock_page)
    assert success is True
    assert "WD-987654" in conf_id or "CONFIRMED" in conf_id or "SUBMIT" in conf_id
