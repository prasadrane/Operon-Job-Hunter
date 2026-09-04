"""Unit tests for PreflightScreener: Live-form knockout scan, immigration screening check, and jurisdiction rules."""

import importlib
import json
import pytest
from playwright.sync_api import sync_playwright

screener_mod = importlib.import_module("src.pipeline.4_submission.preflight_screener")
PreflightScreener = screener_mod.PreflightScreener
PreflightStatus = screener_mod.PreflightStatus


def test_knockout_visa_sponsorship_detection():
    """Verify screener detects explicit no-sponsorship knockouts on live page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        html = """
        <html>
            <body>
                <form>
                    <h3>Application Form</h3>
                    <p>Note: We are unable to provide sponsorship for employment visa status now or in the future.</p>
                    <label>Will you now or in the future require sponsorship?</label>
                    <input type="radio" name="sponsorship" value="yes" /> Yes
                    <input type="radio" name="sponsorship" value="no" /> No
                </form>
            </body>
        </html>
        """
        page.set_content(html)
        screener = PreflightScreener()
        profile = {"requires_sponsorship": True, "us_work_authorized": True, "location": "Chicago, IL"}
        
        result = screener.screen_page(page, company="Acme Corp", profile=profile)
        assert result.status == PreflightStatus.KNOCKOUT_DISQUALIFIED
        assert "sponsorship" in result.reason.lower()
        browser.close()


def test_unlawful_immigration_status_screening_warning():
    """Verify screener warns on citizenship/permanent residency status screening vs work authorization."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        html = """
        <html>
            <body>
                <form>
                    <label for="citizen">Are you a U.S. Citizen or Permanent Resident (Green Card Holder)?</label>
                    <select id="citizen">
                        <option value="yes">Yes</option>
                        <option value="no">No</option>
                    </select>
                </form>
            </body>
        </html>
        """
        page.set_content(html)
        screener = PreflightScreener()
        profile = {"requires_sponsorship": True, "us_work_authorized": True, "location": "New York, NY"}
        
        result = screener.screen_page(page, company="Test Corp", profile=profile)
        assert result.has_status_screening_warning is True
        assert "immigration status" in result.status_screening_details.lower()
        browser.close()


def test_prohibited_salary_history_check():
    """Verify screener flags prohibited salary history questions in jurisdictions banning them."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        html = """
        <html>
            <body>
                <form>
                    <label for="past_comp">What was your previous salary or total compensation at your last job?</label>
                    <input id="past_comp" type="text" />
                </form>
            </body>
        </html>
        """
        page.set_content(html)
        screener = PreflightScreener()
        profile = {"requires_sponsorship": True, "us_work_authorized": True, "location": "San Francisco, CA"}
        
        result = screener.screen_page(page, company="Bay Area Tech", profile=profile)
        assert result.has_prohibited_content_warning is True
        assert "salary history" in result.prohibited_content_details.lower()
        browser.close()


def test_blacklist_and_clean_preflight(tmp_path):
    """Verify blacklist blocking and clean approval for compliant postings."""
    blacklist_file = tmp_path / "blacklist.json"
    blacklist_file.write_text(json.dumps(["BadCompany", "ScamCorp"]))

    screener = PreflightScreener(blacklist_path=str(blacklist_file))
    profile = {"requires_sponsorship": True, "us_work_authorized": True, "location": "Austin, TX"}

    # 1. Blacklisted company
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<html><body><h1>Welcome</h1></body></html>")
        
        result_blacklisted = screener.screen_page(page, company="BadCompany", profile=profile)
        assert result_blacklisted.status == PreflightStatus.BLACKLISTED

        # 2. Clean compliant page
        page.set_content("""
        <html>
            <body>
                <form>
                    <label for="auth">Are you legally authorized to work in the United States?</label>
                    <select id="auth"><option>Yes</option><option>No</option></select>
                </form>
            </body>
        </html>
        """)
        result_clean = screener.screen_page(page, company="GoodCompany", profile=profile)
        assert result_clean.status == PreflightStatus.PASSED
        browser.close()
