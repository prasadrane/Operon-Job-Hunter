"""Unit tests for FormHealingEngine: dynamic locator recovery, validation diagnosis, and pointer cascades."""

import importlib
import pytest
from playwright.sync_api import sync_playwright

from src.core.db.telemetry_sink import TelemetrySink

healing_mod = importlib.import_module("src.pipeline.4_submission.form_healing_engine")
FormHealingEngine = healing_mod.FormHealingEngine
HealingAction = healing_mod.HealingAction
HealingEvent = healing_mod.HealingEvent


def test_validation_error_extraction():
    """Verify extraction of visible validation errors and aria-describedby references."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        html = """
        <html>
            <body>
                <form>
                    <input id="phone_field" aria-invalid="true" aria-describedby="phone_err" value="abc" />
                    <div id="phone_err" class="error-msg">Please enter a valid 10-digit phone number</div>
                    <div class="invalid-feedback">Resume file format must be PDF</div>
                </form>
            </body>
        </html>
        """
        page.set_content(html)
        engine = FormHealingEngine()
        errors = engine.extract_validation_errors(page)
        
        assert len(errors) >= 2
        assert any("10-digit phone" in e for e in errors)
        assert any("Resume file format" in e for e in errors)
        browser.close()


def test_phone_number_auto_formatting_recovery():
    """Verify auto-formatting sanitizes phone numbers based on common validation constraints."""
    engine = FormHealingEngine()
    raw_phone = "+1 (555) 234-5678"
    
    # Error: 10 digits
    formatted_10 = engine.auto_format_value("phone", raw_phone, "Phone must be exactly 10 digits")
    assert formatted_10 == "5552345678"
    
    # Error: numbers only with country code
    formatted_e164 = engine.auto_format_value("phone", raw_phone, "Include country code e.g. +15552345678")
    assert formatted_e164 == "+15552345678"


def test_dynamic_locator_recovery():
    """Verify dynamic locator recovery finds non-standard inputs and fills them."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        html = """
        <html>
            <body>
                <form>
                    <label for="custom_candidate_given_name">Legal First Name</label>
                    <input id="custom_candidate_given_name" name="custom_given_name" type="text" />
                </form>
            </body>
        </html>
        """
        page.set_content(html)
        engine = FormHealingEngine()
        
        # Standard selectors like #first_name will fail
        recovered_sel = engine.recover_locator(page, "first_name", ["#first_name", "input[name='first_name']"])
        assert recovered_sel is not None
        assert "custom_candidate_given_name" in recovered_sel or "custom_given_name" in recovered_sel
        
        # Perform healed fill
        success = engine.healed_fill(page, "first_name", "Alex", ["#first_name"])
        assert success is True
        assert page.input_value("#custom_candidate_given_name") == "Alex"
        
        browser.close()


def test_pointer_event_cascade_dispatch():
    """Verify pointer cascade dispatches native pointer/mouse sequence when standard clicks are blocked."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        html = """
        <html>
            <body>
                <div id="status">idle</div>
                <div id="target_overlay" data-automation-id="click_filter" aria-label="Submit Application" style="cursor:pointer;">
                    Click Me
                </div>
                <script>
                    const el = document.getElementById('target_overlay');
                    el.addEventListener('click', () => {
                        document.getElementById('status').innerText = 'clicked_via_event';
                    });
                </script>
            </body>
        </html>
        """
        page.set_content(html)
        engine = FormHealingEngine()
        
        clicked = engine.dispatch_pointer_cascade(page, '#target_overlay')
        assert clicked is True
        assert page.inner_text("#status") == "clicked_via_event"
        
        browser.close()


def test_healing_event_record_creation():
    """Verify healing event creates structured telemetry payload."""
    engine = FormHealingEngine()
    event = engine.create_healing_event(
        company="Capital One",
        portal_type="workday",
        field_name="phone",
        original_selector="#phone",
        healed_selector="input[data-automation-id='phone-number']",
        action=HealingAction.SELECTOR_RECOVERY,
        details="Auto-recovered from AXTree label match",
    )
    
    assert event.company == "Capital One"
    assert event.portal_type == "workday"
    assert event.action == HealingAction.SELECTOR_RECOVERY
    assert event.healed_selector == "input[data-automation-id='phone-number']"
    payload = event.to_dict()
    assert payload["event"] == "form_healing_event"
    assert payload["metadata"]["field_name"] == "phone"
