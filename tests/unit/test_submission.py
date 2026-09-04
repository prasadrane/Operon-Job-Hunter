"""Unit tests for Stage 4: Persistent Playwright Browser Submitter & ATS Adapters."""

import importlib
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from src.core.models import JobPosting, JobStatus, TailoredArtifacts, SubmissionReceipt, CandidateProfile

# Dynamic imports because module directories start with digits (4_submission)
bm_mod = importlib.import_module("src.pipeline.4_submission.browser_manager")
BrowserManager = bm_mod.BrowserManager

ch_mod = importlib.import_module("src.pipeline.4_submission.captcha_handler")
CaptchaHandler = ch_mod.CaptchaHandler

base_mod = importlib.import_module("src.pipeline.4_submission.adapters.base_adapter")
BaseATSAdapter = base_mod.BaseATSAdapter
CONFIRMATION_INDICATORS = base_mod.CONFIRMATION_INDICATORS

gh_mod = importlib.import_module("src.pipeline.4_submission.adapters.greenhouse")
GreenhouseAdapter = gh_mod.GreenhouseAdapter

lever_mod = importlib.import_module("src.pipeline.4_submission.adapters.lever")
LeverAdapter = lever_mod.LeverAdapter

ashby_mod = importlib.import_module("src.pipeline.4_submission.adapters.ashby")
AshbyAdapter = ashby_mod.AshbyAdapter

wd_mod = importlib.import_module("src.pipeline.4_submission.adapters.workday")
WorkdayAdapter = wd_mod.WorkdayAdapter

wd_ag_mod = importlib.import_module("src.pipeline.4_submission.adapters.workday_agentic")
WorkdayAgenticSubmitter = wd_ag_mod.WorkdayAgenticSubmitter

gen_mod = importlib.import_module("src.pipeline.4_submission.adapters.generic")
GenericAdapter = gen_mod.GenericAdapter

adapters_pkg = importlib.import_module("src.pipeline.4_submission.adapters")
get_adapter = adapters_pkg.get_adapter
ATS_ADAPTERS = adapters_pkg.ATS_ADAPTERS

engine_mod = importlib.import_module("src.pipeline.4_submission.submitter_engine")
SubmitterEngine = engine_mod.SubmitterEngine


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_profile():
    return CandidateProfile(
        first_name="Alex",
        last_name="Rivera",
        full_name="Alex Rivera",
        email="alex.rivera@example.com",
        phone="+1 (555) 019-2834",
        location="Chicago, IL",
        address="123 Michigan Ave",
        city="Chicago",
        state="IL",
        zip_code="60601",
        linkedin="https://linkedin.com/in/alex-rivera",
        github="https://github.com/alexrivera",
        portfolio="https://alexrivera.dev",
        website="https://alexrivera.dev",
        password="TestPassword123!",
        us_work_authorized=True,
        requires_sponsorship=True
    )


@pytest.fixture
def sample_job():
    return JobPosting(
        id="job_gh_001",
        company="Stripe",
        title="Staff Backend Engineer",
        url="https://boards.greenhouse.io/stripe/jobs/123456",
        portal_type="greenhouse",
        source="scanner",
        status=JobStatus.TAILORED
    )


@pytest.fixture
def sample_artifacts(tmp_path):
    resume_file = tmp_path / "Alex_Rivera_Resume.pdf"
    resume_file.write_bytes(b"%PDF-1.4 mock resume content")
    return TailoredArtifacts(
        job_id="job_gh_001",
        resume_pdf_path=str(resume_file),
        qa_answers={
            "years_of_experience": "10+",
            "sponsorship_required": "Yes",
            "authorized_to_work": "Yes",
            "salary_expectation": "$185,000",
            "how_did_you_hear": "LinkedIn"
        },
        linkedin_outreach="Hi Hiring Manager, excited about this role!"
    )


# ============================================================================
# 1. BrowserManager Tests
# ============================================================================

def test_browser_manager_init(tmp_path):
    custom_dir = str(tmp_path / "custom_browser_profile")
    manager = BrowserManager(user_data_dir=custom_dir, headless=True)
    assert manager.user_data_dir == custom_dir
    assert manager.headless is True
    assert os.path.exists(custom_dir)


def test_browser_manager_clean_stale_locks(tmp_path):
    profile_dir = tmp_path / "test_profile"
    profile_dir.mkdir()
    lock1 = profile_dir / "SingletonLock"
    lock2 = profile_dir / "SingletonSocket"
    lock3 = profile_dir / "lockfile"
    normal_file = profile_dir / "Cookies"

    lock1.write_text("lock")
    lock2.write_text("socket")
    lock3.write_text("lockfile")
    normal_file.write_text("cookies_data")

    manager = BrowserManager(user_data_dir=str(profile_dir), headless=True)
    manager._clean_stale_locks()

    assert not lock1.exists()
    assert not lock2.exists()
    assert not lock3.exists()
    assert normal_file.exists()


def test_browser_manager_launch_persistent_context(tmp_path):
    manager = BrowserManager(user_data_dir=str(tmp_path / "profile"), headless=True)
    mock_playwright = MagicMock()
    mock_context = MagicMock()
    mock_playwright.chromium.launch_persistent_context.return_value = mock_context

    context = manager.create_context(mock_playwright)
    assert context == mock_context
    mock_playwright.chromium.launch_persistent_context.assert_called_once()
    call_kwargs = mock_playwright.chromium.launch_persistent_context.call_args.kwargs
    assert call_kwargs["headless"] is True
    assert "--disable-blink-features=AutomationControlled" in call_kwargs["args"]
    # Patchright handles anti-detection natively — no init script injection needed
    assert not mock_context.add_init_script.called


# ============================================================================
# 2. CaptchaHandler Tests
# ============================================================================

def test_captcha_handler_detect_turnstile():
    handler = CaptchaHandler()
    mock_page = MagicMock()
    # Locator returns matches for cloudflare turnstile
    mock_page.locator.side_effect = lambda sel: MagicMock(count=lambda: 1 if "turnstile" in sel or "cf-" in sel else 0)
    mock_page.content.return_value = '<html><body><div class="cf-turnstile"></div></body></html>'

    assert handler.detect_captcha(mock_page) is True


def test_captcha_handler_detect_recaptcha():
    handler = CaptchaHandler()
    mock_page = MagicMock()
    mock_page.locator.side_effect = lambda sel: MagicMock(count=lambda: 1 if "recaptcha" in sel or "g-recaptcha" in sel else 0)
    mock_page.content.return_value = '<html><body><div class="g-recaptcha"></div></body></html>'

    assert handler.detect_captcha(mock_page) is True


def test_captcha_handler_detect_hcaptcha():
    handler = CaptchaHandler()
    mock_page = MagicMock()
    mock_page.locator.side_effect = lambda sel: MagicMock(count=lambda: 1 if "hcaptcha" in sel else 0)
    mock_page.content.return_value = '<html><body><iframe src="https://hcaptcha.com/check"></iframe></body></html>'

    assert handler.detect_captcha(mock_page) is True


def test_captcha_handler_detect_clean_page():
    handler = CaptchaHandler()
    mock_page = MagicMock()
    mock_page.locator.return_value = MagicMock(count=lambda: 0)
    mock_page.content.return_value = '<html><body><h1>Apply for Job</h1><form></form></body></html>'

    assert handler.detect_captcha(mock_page) is False


def test_captcha_handler_wait_for_human_solve_success():
    handler = CaptchaHandler()
    mock_page = MagicMock()
    # First check detects captcha, second check detects none (user solved it)
    detection_results = [True, False]
    with patch.object(handler, "detect_captcha", side_effect=detection_results):
        with patch("time.sleep", return_value=None):
            solved = handler.wait_for_human_solve(mock_page, timeout_sec=5, poll_interval=0.1)
            assert solved is True


def test_captcha_handler_wait_for_human_solve_timeout():
    handler = CaptchaHandler()
    mock_page = MagicMock()
    times = [100.0, 101.0, 102.0, 110.0, 115.0, 120.0, 130.0]
    idx = 0

    def fake_time():
        nonlocal idx
        val = times[min(idx, len(times) - 1)]
        idx += 1
        return val

    with patch.object(handler, "detect_captcha", return_value=True), \
         patch("time.sleep", return_value=None), \
         patch("time.time", side_effect=fake_time):
        solved = handler.wait_for_human_solve(mock_page, timeout_sec=5, poll_interval=0.1)
        assert solved is False


# ============================================================================
# 3. Adapter Dispatcher Tests
# ============================================================================

def test_adapter_dispatcher_matching():
    assert isinstance(get_adapter("https://boards.greenhouse.io/stripe/jobs/123"), GreenhouseAdapter)
    assert isinstance(get_adapter("https://jobs.lever.co/databricks/abc"), LeverAdapter)
    assert isinstance(get_adapter("https://jobs.ashbyhq.com/linear/456"), AshbyAdapter)
    assert isinstance(get_adapter("https://capitalone.wd1.myworkdayjobs.com/en-US/Careers/job/1"), WorkdayAgenticSubmitter)
    assert isinstance(get_adapter("https://careers.unknowncompany.com/apply"), GenericAdapter)


def test_base_adapter_verify_submission_indicators():
    adapter = GenericAdapter()
    mock_page = MagicMock()

    # Test URL redirect confirmation
    mock_page.url = "https://boards.greenhouse.io/stripe/jobs/123/confirmation"
    mock_page.content.return_value = "<html><body>Form</body></html>"
    assert adapter.verify_submission(mock_page) is True

    # Test Content confirmation indicator
    mock_page.url = "https://boards.greenhouse.io/stripe/jobs/123"
    mock_page.content.return_value = "<html><body><h1>Thank you for applying!</h1>We will review your application.</body></html>"
    assert adapter.verify_submission(mock_page) is True

    # Test Unsubmitted page
    mock_page.url = "https://boards.greenhouse.io/stripe/jobs/123"
    mock_page.content.return_value = "<html><body><h1>Apply Now</h1><input name='name'/></body></html>"
    assert adapter.verify_submission(mock_page) is False


# ============================================================================
# 4. GreenhouseAdapter Tests
# ============================================================================

def test_greenhouse_can_handle():
    gh = GreenhouseAdapter()
    assert gh.can_handle("https://boards.greenhouse.io/stripe/jobs/123") is True
    assert gh.can_handle("https://job-boards.greenhouse.io/openai/jobs/456") is True
    assert gh.can_handle("https://jobs.lever.co/test") is False


def test_greenhouse_fill_form(sample_job, sample_artifacts, sample_profile):
    gh = GreenhouseAdapter()
    mock_page = MagicMock()
    mock_page.frames = []
    
    # Mock locator visibility and inputs
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_page.locator.return_value = mock_locator
    mock_page.is_visible.return_value = True

    filled = gh.fill_form(mock_page, sample_job, sample_artifacts, sample_profile)
    assert filled is True
    assert mock_page.fill.called
    assert mock_locator.first.set_input_files.called


def test_greenhouse_submit(sample_job):
    gh = GreenhouseAdapter()
    mock_page = MagicMock()
    mock_page.url = "https://boards.greenhouse.io/stripe/jobs/123/confirmation"
    mock_page.content.return_value = "Thank you for applying! Confirmation ID: GH-9921"
    mock_page.is_visible.return_value = True

    with patch("time.sleep", return_value=None):
        success, confirmation_id = gh.submit(mock_page)
        assert success is True
        assert "GH-9921" in confirmation_id or "confirmation" in confirmation_id.lower() or "submitted" in confirmation_id.lower()


# ============================================================================
# 5. LeverAdapter Tests
# ============================================================================

def test_lever_can_handle():
    lever = LeverAdapter()
    assert lever.can_handle("https://jobs.lever.co/anthropic/123") is True
    assert lever.can_handle("https://lever.co/apply") is True
    assert lever.can_handle("https://boards.greenhouse.io/test") is False


def test_lever_fill_form(sample_job, sample_artifacts, sample_profile):
    lever = LeverAdapter()
    mock_page = MagicMock()
    mock_page.frames = []
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_page.locator.return_value = mock_locator
    mock_page.is_visible.return_value = True

    filled = lever.fill_form(mock_page, sample_job, sample_artifacts, sample_profile)
    assert filled is True
    assert mock_page.fill.called
    assert mock_locator.first.set_input_files.called


def test_lever_submit():
    lever = LeverAdapter()
    mock_page = MagicMock()
    mock_page.url = "https://jobs.lever.co/anthropic/123/thanks"
    mock_page.content.return_value = "Application submitted! Thank you for applying."
    mock_page.is_visible.return_value = True

    with patch("time.sleep", return_value=None):
        success, confirmation_id = lever.submit(mock_page)
        assert success is True
        assert len(confirmation_id) > 0


# ============================================================================
# 6. AshbyAdapter Tests
# ============================================================================

def test_ashby_can_handle():
    ashby = AshbyAdapter()
    assert ashby.can_handle("https://jobs.ashbyhq.com/linear/123") is True
    assert ashby.can_handle("https://ashbyhq.com/careers") is True
    assert ashby.can_handle("https://jobs.lever.co/test") is False


def test_ashby_fill_form(sample_job, sample_artifacts, sample_profile):
    ashby = AshbyAdapter()
    mock_page = MagicMock()
    mock_page.frames = []
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_page.locator.return_value = mock_locator
    mock_page.is_visible.return_value = True

    filled = ashby.fill_form(mock_page, sample_job, sample_artifacts, sample_profile)
    assert filled is True
    assert mock_page.fill.called
    assert mock_locator.first.set_input_files.called


def test_ashby_submit():
    ashby = AshbyAdapter()
    mock_page = MagicMock()
    mock_page.url = "https://jobs.ashbyhq.com/linear/123/success"
    mock_page.content.return_value = "Your application has been submitted successfully."
    mock_page.is_visible.return_value = True

    with patch("time.sleep", return_value=None):
        success, confirmation_id = ashby.submit(mock_page)
        assert success is True
        assert len(confirmation_id) > 0


# ============================================================================
# 7. WorkdayAdapter Tests
# ============================================================================

def test_workday_can_handle():
    wd = WorkdayAdapter()
    assert wd.can_handle("https://capitalone.wd1.myworkdayjobs.com/Capital_One/job/123") is True
    assert wd.can_handle("https://fidelity.myworkdayjobs.com/careers") is True
    assert wd.can_handle("https://boards.greenhouse.io/test") is False


def test_workday_safe_click_multitier():
    wd = WorkdayAdapter()
    mock_page = MagicMock()

    # Tier 1 visible
    mock_page.is_visible.return_value = True
    clicked = wd.safe_click(mock_page, "Submit")
    assert clicked is True
    mock_page.click.assert_called()

    # Tier 2 JS evaluation fallback
    mock_page.is_visible.return_value = False
    mock_page.evaluate.return_value = True
    clicked_js = wd.safe_click(mock_page, "Next")
    assert clicked_js is True
    mock_page.evaluate.assert_called()


def test_workday_fill_form_and_wizard(sample_job, sample_artifacts, sample_profile):
    wd = WorkdayAdapter()
    mock_page = MagicMock()
    mock_page.frames = []
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_locator.first.is_visible.return_value = True
    mock_page.locator.return_value = mock_locator
    mock_page.is_visible.return_value = True

    with patch("time.sleep", return_value=None):
        filled = wd.fill_form(mock_page, sample_job, sample_artifacts, sample_profile)
        assert filled is True


def test_workday_submit():
    wd = WorkdayAdapter()
    mock_page = MagicMock()
    mock_page.url = "https://company.myworkdayjobs.com/job/123/applied"
    mock_page.content.return_value = "Thank you for your application. Application received."
    mock_page.is_visible.return_value = True

    with patch("time.sleep", return_value=None):
        success, confirmation_id = wd.submit(mock_page)
        assert success is True
        assert len(confirmation_id) > 0


# ============================================================================
# 8. GenericAdapter Tests
# ============================================================================

def test_generic_can_handle():
    gen = GenericAdapter()
    assert gen.can_handle("https://anycompany.com/apply") is True
    assert gen.can_handle("https://careers.startup.io/form") is True


def test_generic_fill_form_fuzzy_matching(sample_job, sample_artifacts, sample_profile):
    gen = GenericAdapter()
    mock_page = MagicMock()
    mock_page.frames = []
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_page.locator.return_value = mock_locator
    mock_page.is_visible.return_value = True

    filled = gen.fill_form(mock_page, sample_job, sample_artifacts, sample_profile)
    assert filled is True
    assert mock_page.fill.called


def test_generic_submit():
    gen = GenericAdapter()
    mock_page = MagicMock()
    mock_page.url = "https://anycompany.com/apply/thank-you"
    mock_page.content.return_value = "Thank you! Application complete."
    mock_page.is_visible.return_value = True

    with patch("time.sleep", return_value=None):
        success, confirmation_id = gen.submit(mock_page)
        assert success is True


# ============================================================================
# 9. SubmitterEngine Orchestration Tests
# ============================================================================

def test_submitter_engine_successful_run(sample_job, sample_artifacts, sample_profile, tmp_path):
    receipts_dir = tmp_path / "receipts"
    engine = SubmitterEngine(
        browser_manager=MagicMock(),
        captcha_handler=MagicMock(),
        receipts_dir=str(receipts_dir)
    )

    mock_page = MagicMock()
    mock_page.url = "https://boards.greenhouse.io/stripe/jobs/123"
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    engine.browser_manager.create_context.return_value = mock_context
    engine.captcha_handler.detect_captcha.return_value = False

    # Mock adapter
    mock_adapter = MagicMock(spec=GreenhouseAdapter)
    mock_adapter.fill_form.return_value = True
    mock_adapter.submit.return_value = (True, "CONF-STRIPE-8821")

    with patch.object(engine_mod, "get_adapter", return_value=mock_adapter), \
         patch.object(engine_mod, "sync_playwright") as mock_playwright_ctx:
        
        mock_p = MagicMock()
        mock_playwright_ctx.return_value.__enter__.return_value = mock_p

        receipt = engine.submit(sample_job, sample_artifacts, sample_profile)
        assert receipt.success is True
        assert receipt.job_id == sample_job.id
        assert receipt.confirmation_id == "CONF-STRIPE-8821"
        assert receipt.screenshot_path is not None
        assert mock_page.screenshot.called


def test_submitter_engine_captcha_solved(sample_job, sample_artifacts, sample_profile, tmp_path):
    engine = SubmitterEngine(
        browser_manager=MagicMock(),
        captcha_handler=MagicMock(),
        receipts_dir=str(tmp_path / "receipts")
    )
    mock_page = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    engine.browser_manager.create_context.return_value = mock_context

    # Captcha detected then human solves it
    engine.captcha_handler.detect_captcha.return_value = True
    engine.captcha_handler.wait_for_human_solve.return_value = True

    mock_adapter = MagicMock()
    mock_adapter.fill_form.return_value = True
    mock_adapter.submit.return_value = (True, "CONF-CAPTCHA-SOLVED")

    with patch.object(engine_mod, "get_adapter", return_value=mock_adapter), \
         patch.object(engine_mod, "sync_playwright") as mock_playwright_ctx:
        
        mock_p = MagicMock()
        mock_playwright_ctx.return_value.__enter__.return_value = mock_p

        receipt = engine.submit(sample_job, sample_artifacts, sample_profile)
        assert receipt.success is True
        assert engine.captcha_handler.wait_for_human_solve.called


def test_submitter_engine_captcha_timeout_failure(sample_job, sample_artifacts, sample_profile, tmp_path):
    engine = SubmitterEngine(
        browser_manager=MagicMock(),
        captcha_handler=MagicMock(),
        receipts_dir=str(tmp_path / "receipts")
    )
    mock_page = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    engine.browser_manager.create_context.return_value = mock_context

    # Captcha detected and human solve times out
    engine.captcha_handler.detect_captcha.return_value = True
    engine.captcha_handler.wait_for_human_solve.return_value = False

    with patch.object(engine_mod, "sync_playwright") as mock_playwright_ctx:
        mock_p = MagicMock()
        mock_playwright_ctx.return_value.__enter__.return_value = mock_p

        receipt = engine.submit(sample_job, sample_artifacts, sample_profile)
        assert receipt.success is False
        assert "CAPTCHA" in receipt.error_message


def test_submitter_engine_dry_run(sample_job, sample_artifacts, sample_profile, tmp_path):
    engine = SubmitterEngine(
        browser_manager=MagicMock(),
        captcha_handler=MagicMock(),
        receipts_dir=str(tmp_path / "receipts"),
        dry_run=True
    )
    mock_page = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    engine.browser_manager.create_context.return_value = mock_context
    engine.captcha_handler.detect_captcha.return_value = False

    mock_adapter = MagicMock()
    mock_adapter.fill_form.return_value = True

    with patch.object(engine_mod, "get_adapter", return_value=mock_adapter), \
         patch.object(engine_mod, "sync_playwright") as mock_playwright_ctx:
        
        mock_p = MagicMock()
        mock_playwright_ctx.return_value.__enter__.return_value = mock_p

        receipt = engine.submit(sample_job, sample_artifacts, sample_profile)
        assert receipt.success is True
        assert "dry_run" in receipt.confirmation_id.lower()
        assert not mock_adapter.submit.called

