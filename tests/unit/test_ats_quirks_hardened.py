"""Unit tests for hardened ATS quirks: Lever hCaptcha checkbox avoidance, Ashby dedup aliases, and Workday cascades."""

import importlib
import pytest
from playwright.sync_api import sync_playwright

lever_mod = importlib.import_module("src.pipeline.4_submission.adapters.lever")
LeverAdapter = lever_mod.LeverAdapter

ashby_mod = importlib.import_module("src.pipeline.4_submission.adapters.ashby")
AshbyAdapter = ashby_mod.AshbyAdapter

workday_mod = importlib.import_module("src.pipeline.4_submission.adapters.workday")
WorkdayAdapter = workday_mod.WorkdayAdapter


def test_lever_adapter_skips_checkboxes_to_evade_hcaptcha():
    """Verify Lever adapter fills text inputs but skips programmatic clicks on checkboxes and radios."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        html = """
        <html>
            <body>
                <form id="application-form">
                    <input type="text" name="name" id="name" />
                    <input type="email" name="email" id="email" />
                    <input type="checkbox" id="consent_checkbox" name="consent" />
                    <input type="radio" name="work_auth" value="yes" />
                </form>
            </body>
        </html>
        """
        page.set_content(html)
        adapter = LeverAdapter()
        profile = {"full_name": "Alex Rivera", "email": "alex.rivera@example.com"}

        filled = adapter.fill_profile(page, profile)
        assert filled is True
        assert page.input_value("input[name='name']") == "Alex Rivera"
        assert page.input_value("input[name='email']") == "alex.rivera@example.com"
        
        # Verify checkboxes/radios were NOT clicked programmatically
        assert page.is_checked("#consent_checkbox") is False
        assert page.is_checked("input[name='work_auth']") is False

        browser.close()


def test_ashby_adapter_generates_email_alias_on_repeat_application():
    """Verify Ashby adapter generates email alias (user+company@domain.com) when candidate previously applied."""
    adapter = AshbyAdapter()
    
    # 1. First time application
    email_first = adapter.get_effective_email(
        email="alex.rivera@example.com",
        company="Databricks",
        prior_applications=[],
    )
    assert email_first == "alex.rivera@example.com"

    # 2. Second application to same company
    email_repeat = adapter.get_effective_email(
        email="alex.rivera@example.com",
        company="Databricks",
        prior_applications=["Databricks"],
    )
    assert email_repeat == "alex.rivera+databricks@example.com"


def test_workday_adapter_pointer_cascade_on_click_filter():
    """Verify Workday adapter dispatches pointer cascade on click_filter overlay divs."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        html = """
        <html>
            <body>
                <div id="status">unclicked</div>
                <div data-automation-id="click_filter" aria-label="Save and Continue" style="cursor:pointer;">
                    Save and Continue
                </div>
                <script>
                    const el = document.querySelector('[data-automation-id="click_filter"]');
                    el.addEventListener('click', () => {
                        document.getElementById('status').innerText = 'cascade_success';
                    });
                </script>
            </body>
        </html>
        """
        page.set_content(html)
        adapter = WorkdayAdapter()

        clicked = adapter.safe_click(page, "Save and Continue")
        assert clicked is True
        assert page.inner_text("#status") == "cascade_success"

        browser.close()
