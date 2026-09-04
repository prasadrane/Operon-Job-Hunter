"""Unit tests for FastPath Submitter, DOM Quiescence, and dynamic Mock ATS Server fixture."""

import importlib
import os
import socket
import tempfile
import time
import pytest
from playwright.sync_api import sync_playwright

from tests.fixtures.mock_ats_server import MockATSServer

dom_mod = importlib.import_module("src.pipeline.4_submission.dom_quiescence")
wait_for_dom_quiescence = dom_mod.wait_for_dom_quiescence

fastpath_mod = importlib.import_module("src.pipeline.4_submission.fastpath_engine")
FastPathSubmitter = fastpath_mod.FastPathSubmitter
PORTAL_SELECTORS = fastpath_mod.PORTAL_SELECTORS


@pytest.fixture(scope="module")
def ats_server():
    """Start Mock ATS server on an ephemeral dynamic port."""
    server = MockATSServer(port=0)  # port=0 triggers ephemeral port binding
    server.start()
    time.sleep(0.5)
    yield server
    server.stop()


def test_mock_ats_server_ephemeral_port_allocation():
    """Verify MockATSServer binds to a dynamic non-zero ephemeral port and serves responses."""
    server = MockATSServer(port=0)
    server.start()
    try:
        assert server.port > 0
        base_url = server.get_base_url()
        assert base_url.startswith(f"http://127.0.0.1:{server.port}")
    finally:
        server.stop()


def test_wait_for_dom_quiescence_resilience():
    """Verify wait_for_dom_quiescence handles mock page objects and debounces cleanly."""
    class FakePage:
        def __init__(self):
            self.waited = 0

        def wait_for_load_state(self, state, timeout=1000):
            self.waited += 1

    fake_page = FakePage()
    start = time.perf_counter()
    wait_for_dom_quiescence(fake_page, debounce_ms=100, max_timeout_s=1.0)
    elapsed = time.perf_counter() - start
    assert fake_page.waited >= 1
    assert elapsed >= 0.09


def test_greenhouse_fastpath_autofill_and_submission(ats_server, tmp_path):
    """Verify Greenhouse autofill across first_name, last_name, email, phone, linkedin_url, and file attachment with receipt extraction."""
    resume_file = tmp_path / "test_resume.pdf"
    resume_file.write_bytes(b"%PDF-1.4 Mock Candidate Resume Data")

    profile = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane.doe@example.com",
        "phone": "+1 (555) 234-5678",
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "location": "San Francisco, CA"
    }

    url = f"{ats_server.get_base_url()}/greenhouse/test_job"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        submitter = FastPathSubmitter()
        filled = submitter.fill_profile(page, profile, resume_path=str(resume_file))
        assert filled is True

        # Verify DOM values
        assert page.input_value("#first_name") == "Jane"
        assert page.input_value("#last_name") == "Doe"
        assert page.input_value("#email") == "jane.doe@example.com"
        assert page.input_value("#phone") == "+1 (555) 234-5678"
        assert page.input_value("#job_application_answers_attributes_0_text_value") == "https://linkedin.com/in/janedoe"

        # Verify submission receipt extraction
        receipt = submitter.submit(page)
        assert receipt["success"] is True
        assert "GH-CONF-9876" in receipt["confirmation_id"]

        browser.close()


def test_lever_fastpath_autofill_and_submission(ats_server, tmp_path):
    """Verify Lever autofill and submission receipt extraction."""
    resume_file = tmp_path / "jane_lever_resume.pdf"
    resume_file.write_bytes(b"%PDF-1.4 Mock Candidate Resume Data for Lever")

    profile = {
        "first_name": "Jane",
        "last_name": "Doe",
        "full_name": "Jane Doe",
        "email": "jane.doe@levertest.com",
        "phone": "+1 (555) 987-6543",
        "linkedin": "https://linkedin.com/in/janedoe-lever",
        "location": "New York, NY"
    }

    url = f"{ats_server.get_base_url()}/lever/test_job"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        submitter = FastPathSubmitter()
        filled = submitter.fill_profile(page, profile, resume_path=str(resume_file))
        assert filled is True

        # Verify DOM values
        assert page.input_value("input[name='name']") == "Jane Doe"
        assert page.input_value("input[name='email']") == "jane.doe@levertest.com"
        assert page.input_value("input[name='phone']") == "+1 (555) 987-6543"
        assert page.input_value("input[name='urls[LinkedIn]']") == "https://linkedin.com/in/janedoe-lever"

        # Verify submission receipt extraction
        receipt = submitter.submit(page)
        assert receipt["success"] is True
        assert "LEVER-CONF-5432" in receipt["confirmation_id"]

        browser.close()


def test_fastpath_submit_failure_graceful():
    """Verify submit handles page without submit button gracefully."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<html><body><h1>No submit button here</h1></body></html>")

        submitter = FastPathSubmitter()
        receipt = submitter.submit(page)
        assert receipt["success"] is False
        assert receipt["confirmation_id"] is None

        browser.close()
