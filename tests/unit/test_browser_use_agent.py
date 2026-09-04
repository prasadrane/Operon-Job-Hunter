"""Unit tests for Browser Use submission agent."""

import asyncio
import importlib
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Dynamic imports because module directories start with digits (4_submission)
bua_mod = importlib.import_module("src.pipeline.4_submission.browser_use_agent")
BrowserUseSubmissionAgent = bua_mod.BrowserUseSubmissionAgent
SubmissionTask = bua_mod.SubmissionTask
SubmissionResult = bua_mod.SubmissionResult
CareerGraphController = bua_mod.CareerGraphController
SubmissionError = bua_mod.SubmissionError
AuthError = bua_mod.AuthError
CaptchaError = bua_mod.CaptchaError
TierExhaustedError = bua_mod.TierExhaustedError
AuditEntry = importlib.import_module("src.pipeline.4_submission.submission_audit").AuditEntry


@pytest.fixture
def sample_task():
    """Create a sample SubmissionTask for testing."""
    return SubmissionTask(
        job_url="https://boards.greenhouse.io/testcorp/jobs/12345",
        company="TestCorp",
        title="Software Engineer",
        portal_type="greenhouse",
        job_id="job-test-123",
        profile={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "+1234567890",
        },
        resume_pdf_path="/tmp/test_resume.pdf",
    )


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    try:
        os.unlink(db_path)
    except Exception:
        pass


def test_submission_task_creation(sample_task):
    """Test SubmissionTask Pydantic model creation."""
    assert sample_task.job_url == "https://boards.greenhouse.io/testcorp/jobs/12345"
    assert sample_task.company == "TestCorp"
    assert sample_task.title == "Software Engineer"
    assert sample_task.portal_type == "greenhouse"
    assert sample_task.profile["first_name"] == "John"
    assert sample_task.use_vision == "auto"
    assert sample_task.max_steps == 30
    assert sample_task.timeout_seconds == 90


def test_submission_result_creation():
    """Test SubmissionResult Pydantic model creation."""
    result = SubmissionResult(
        success=True,
        confirmation_id="GH-CONF-ABC123",
        steps_taken=12,
        tokens_used=3500,
        duration_seconds=45.2,
        tier_used="T2",
        audit_trail=[{"action": "navigate", "success": True}],
    )
    assert result.success is True
    assert result.confirmation_id == "GH-CONF-ABC123"
    assert result.steps_taken == 12
    assert result.tier_used == "T2"
    assert len(result.audit_trail) == 1


def test_error_types():
    """Test submission error hierarchy."""
    assert issubclass(AuthError, SubmissionError)
    assert issubclass(CaptchaError, SubmissionError)
    assert issubclass(TierExhaustedError, SubmissionError)
    assert AuthError.retryable is True
    assert CaptchaError.retryable is False
    assert TierExhaustedError.retryable is False


def test_career_graph_controller_init():
    """Test CareerGraphController initialization."""
    controller = CareerGraphController(
        profile={"first_name": "John", "email": "john@example.com"},
        job_context={"company": "TestCorp", "title": "Engineer"},
        submission_id="test-sub-id",
    )
    assert controller.profile["first_name"] == "John"
    assert controller.job_context["company"] == "TestCorp"
    assert controller.submission_id == "test-sub-id"
    assert controller._step_counter == 0


def test_career_graph_controller_audit_callback():
    """Test CareerGraphController audit callback is called."""
    audit_entries = []

    def mock_callback(entry):
        audit_entries.append(entry)

    controller = CareerGraphController(
        profile={"first_name": "John"},
        job_context={"company": "TestCorp", "job_id": "job-1"},
        auditor_callback=mock_callback,
    )

    # Simulate an audit call
    controller._audit("navigate", "https://example.com", True, duration_ms=100.0)

    assert len(audit_entries) == 1
    assert audit_entries[0].action_type == "navigate"
    assert audit_entries[0].target == "https://example.com"
    assert audit_entries[0].success is True
    assert audit_entries[0].step_index == 1
    assert audit_entries[0].tier == "T2"


@pytest.mark.asyncio
async def test_agent_disabled_via_config(sample_task):
    """Test agent returns failure when disabled via config."""
    with patch.object(bua_mod, "get_settings") as mock_settings:
        settings = MagicMock()
        settings.browser_use_enabled = False
        settings.browser_use_vision = "auto"
        settings.browser_use_max_steps = 30
        settings.browser_use_max_failures = 3
        settings.browser_use_timeout_seconds = 90
        settings.primary_llm_provider = "alibaba"
        settings.browser_use_model = "qwen-vl-max"
        settings.alibaba_api_key = "test-key"
        settings.alibaba_base_url = "https://test.api.com"
        settings.browser_use_fallback_provider = "gemini"
        settings.browser_use_fallback_model = "gemini-2.5-flash"
        settings.gemini_api_key = None
        mock_settings.return_value = settings

        agent = BrowserUseSubmissionAgent()
        result = await agent.submit(sample_task)

        assert result.success is False
        assert "disabled" in result.error_message.lower()
        assert result.tier_used == "T2"


@pytest.mark.asyncio
async def test_agent_timeout_handling(sample_task, temp_db):
    """Test agent handles timeout correctly."""
    import sys

    with patch.object(bua_mod, "get_settings") as mock_settings:
        settings = MagicMock()
        settings.browser_use_enabled = True
        settings.browser_use_vision = "auto"
        settings.browser_use_max_steps = 30
        settings.browser_use_max_failures = 3
        settings.browser_use_timeout_seconds = 1  # Very short timeout
        settings.primary_llm_provider = "alibaba"
        settings.browser_use_model = "qwen-vl-max"
        settings.alibaba_api_key = "test-key"
        settings.alibaba_base_url = "https://test.api.com"
        settings.browser_use_fallback_provider = "gemini"
        settings.browser_use_fallback_model = "gemini-2.5-flash"
        settings.gemini_api_key = None
        settings.db_path = temp_db
        mock_settings.return_value = settings

        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(side_effect=asyncio.TimeoutError())

        mock_bu_module = MagicMock()
        mock_bu_module.Agent.return_value = mock_agent_instance

        mock_llm = MagicMock()

        with patch.dict(sys.modules, {"browser_use": mock_bu_module}):
            with patch.object(BrowserUseSubmissionAgent, "_build_llm", return_value=mock_llm):
                agent = BrowserUseSubmissionAgent()
                result = await agent.submit(sample_task)

                assert result.success is False
                assert "timed out" in result.error_message.lower()
                assert result.tier_used == "T2"


@pytest.mark.asyncio
async def test_agent_exception_handling(sample_task):
    """Test agent handles exceptions correctly."""
    import sys

    with patch.object(bua_mod, "get_settings") as mock_settings:
        settings = MagicMock()
        settings.browser_use_enabled = True
        settings.browser_use_vision = "auto"
        settings.browser_use_max_steps = 30
        settings.browser_use_max_failures = 3
        settings.browser_use_timeout_seconds = 90
        settings.primary_llm_provider = "alibaba"
        settings.browser_use_model = "qwen-vl-max"
        settings.alibaba_api_key = "test-key"
        settings.alibaba_base_url = "https://test.api.com"
        settings.browser_use_fallback_provider = "gemini"
        settings.browser_use_fallback_model = "gemini-2.5-flash"
        settings.gemini_api_key = None
        mock_settings.return_value = settings

        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(side_effect=RuntimeError("Browser crashed"))

        mock_bu_module = MagicMock()
        mock_bu_module.Agent.return_value = mock_agent_instance

        mock_llm = MagicMock()

        with patch.dict(sys.modules, {"browser_use": mock_bu_module}):
            with patch.object(BrowserUseSubmissionAgent, "_build_llm", return_value=mock_llm):
                agent = BrowserUseSubmissionAgent()
                result = await agent.submit(sample_task)

                assert result.success is False
                assert "Browser crashed" in result.error_message
                assert result.tier_used == "T2"


def test_build_task_prompt(sample_task):
    """Test task prompt construction."""
    with patch.object(bua_mod, "get_settings") as mock_settings:
        settings = MagicMock()
        settings.browser_use_enabled = True
        settings.browser_use_vision = "auto"
        settings.browser_use_max_steps = 30
        settings.browser_use_max_failures = 3
        settings.browser_use_timeout_seconds = 90
        settings.primary_llm_provider = "alibaba"
        settings.browser_use_model = "qwen-vl-max"
        settings.alibaba_api_key = "test-key"
        settings.alibaba_base_url = "https://test.api.com"
        settings.browser_use_fallback_provider = "gemini"
        settings.browser_use_fallback_model = "gemini-2.5-flash"
        settings.gemini_api_key = None
        mock_settings.return_value = settings

        agent = BrowserUseSubmissionAgent()
        prompt = agent._build_task_prompt(sample_task)

        assert sample_task.job_url in prompt
        assert sample_task.company in prompt
        assert sample_task.title in prompt
        assert "resume PDF" in prompt
        assert "confirmation" in prompt.lower()


def test_task_with_credentials():
    """Test task prompt includes login instructions when credentials provided."""
    task = SubmissionTask(
        job_url="https://example.com/job",
        company="TestCorp",
        title="Engineer",
        profile={"first_name": "John"},
        credentials={"username": "user", "password": "pass"},
    )

    with patch.object(bua_mod, "get_settings") as mock_settings:
        settings = MagicMock()
        settings.browser_use_enabled = True
        settings.browser_use_vision = "auto"
        settings.browser_use_max_steps = 30
        settings.browser_use_max_failures = 3
        settings.browser_use_timeout_seconds = 90
        settings.primary_llm_provider = "alibaba"
        settings.browser_use_model = "qwen-vl-max"
        settings.alibaba_api_key = "test-key"
        settings.alibaba_base_url = "https://test.api.com"
        settings.browser_use_fallback_provider = "gemini"
        settings.browser_use_fallback_model = "gemini-2.5-flash"
        settings.gemini_api_key = None
        mock_settings.return_value = settings

        agent = BrowserUseSubmissionAgent()
        prompt = agent._build_task_prompt(task)

        assert "login" in prompt.lower()
        assert "credentials" in prompt.lower()
