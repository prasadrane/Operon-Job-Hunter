"""Unit tests for Telegram Interactive Bot & Notification Dispatcher."""

from unittest.mock import MagicMock, patch
import pytest
from src.core.models import ApplicationRecord, JobPosting, JobStatus, TailoredArtifacts
from src.interface.bot.telegram_bot import TelegramNotifier


@pytest.fixture
def mock_bot():
    """Fixture providing a mock bot client with send_message, send_document, answer_callback_query."""
    bot = MagicMock()
    bot.send_message.return_value = {"ok": True, "result": {"message_id": 101}}
    bot.send_document.return_value = {"ok": True, "result": {"message_id": 102}}
    bot.answer_callback_query.return_value = {"ok": True}
    return bot


@pytest.fixture
def mock_repos():
    """Fixture providing mock JobRepository, ApplicationRepository, ArtifactRepository."""
    job_repo = MagicMock()
    app_repo = MagicMock()
    artifact_repo = MagicMock()

    sample_job = JobPosting(
        id="job_c1_01",
        company="Capital One",
        title="Senior .NET Engineer",
        url="https://capitalone.careers/job/123",
        status=JobStatus.MATCHED,
        h1b_sponsored=True,
    )
    job_repo.get_job.return_value = sample_job
    job_repo.get_all_jobs.return_value = [sample_job]
    job_repo.get_jobs_by_status.return_value = [sample_job]

    sample_artifact = TailoredArtifacts(
        id="art_job_c1_01",
        job_id="job_c1_01",
        resume_pdf_path="/tmp/resumes/capital_one_alex.pdf",
    )
    artifact_repo.get_by_job_id.return_value = sample_artifact

    return {
        "job_repo": job_repo,
        "app_repo": app_repo,
        "artifact_repo": artifact_repo,
        "sample_job": sample_job,
        "sample_artifact": sample_artifact,
    }


def test_send_match_alert(mock_bot):
    """Test sending formatted job match alert with fit score and H-1B confirmation."""
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", bot_client=mock_bot)
    result = notifier.send_job_match(
        company="Capital One",
        title="Senior .NET Engineer",
        fit_score=92,
        url="https://capitalone.careers/job/123",
        h1b_sponsored=True,
    )

    assert result is True
    assert mock_bot.send_message.called
    call_kwargs = mock_bot.send_message.call_args[1]
    assert call_kwargs["chat_id"] == "12345"
    assert "Capital One" in call_kwargs["text"]
    assert "Senior .NET Engineer" in call_kwargs["text"]
    assert "92" in call_kwargs["text"]
    assert "H-1B" in call_kwargs["text"]


def test_send_match_alert_with_stack_and_reason(mock_bot):
    """Test sending job match alert including stack list and fit reasoning."""
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", bot_client=mock_bot)
    result = notifier.send_job_match(
        company="Discover",
        title="Staff Cloud Architect",
        fit_score=95,
        url="https://discover.careers/job/456",
        h1b_sponsored=False,
        stack=["AWS", "Kubernetes", "Python", ".NET Core"],
        reason="Deep alignment with microservices architecture and AWS ECS experience.",
        job_id="job_disc_01",
    )

    assert result is True
    call_kwargs = mock_bot.send_message.call_args[1]
    text = call_kwargs["text"]
    assert "Discover" in text
    assert "Staff Cloud Architect" in text
    assert "Kubernetes" in text
    assert "Deep alignment" in text
    assert "Not Sponsored" in text or "❌" in text


def test_send_match_alert_with_causal_chain_and_bridge(mock_bot):
    """Test sending job match alert with grounded causal proof and transferable bridge."""
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", bot_client=mock_bot)
    result = notifier.send_job_match(
        company="Stripe",
        title="Senior Platform Engineer",
        fit_score=94,
        url="https://stripe.com/jobs/1",
        h1b_sponsored=True,
        stack=["Kafka", "AWS", "DynamoDB"],
        reason="Strong platform fit.",
        causal_chain="Kafka Match -> Action: Architected governance -> Achieved: 99.99% uptime",
        bridging_statement="While role lists RabbitMQ, candidate brings verified mastery of Distributed Messaging via Kafka.",
    )

    assert result is True
    call_kwargs = mock_bot.send_message.call_args[1]
    text = call_kwargs["text"]
    assert "Grounded Proof" in text
    assert "99.99% uptime" in text
    assert "Transferable Bridge" in text
    assert "RabbitMQ" in text



def test_send_captcha_alert(mock_bot):
    """Test urgent CAPTCHA / 2FA alert dispatch with priority sound."""
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", bot_client=mock_bot)
    result = notifier.send_captcha_alert(
        company="JPMorgan Chase",
        title="Lead Software Engineer",
        captcha_type="Cloudflare Turnstile",
        url="https://jpmc.careers/apply/789",
        timeout_sec=90,
    )

    assert result is True
    assert mock_bot.send_message.called
    call_kwargs = mock_bot.send_message.call_args[1]
    text = call_kwargs["text"]
    assert "CAPTCHA" in text or "Turnstile" in text
    assert "JPMorgan Chase" in text
    assert "90" in text
    assert call_kwargs.get("disable_notification") is False


def test_send_review_gate(mock_bot):
    """Test review gate notification with inline action buttons."""
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", bot_client=mock_bot)
    result = notifier.send_review_gate(
        job_id="job_amzn_10",
        company="Amazon",
        title="Principal Systems Engineer",
        fit_score=88,
        url="https://amazon.jobs/en/jobs/10",
        resume_pdf_path="/path/to/resume.pdf",
        match_reason="Matches high throughput distributed systems requirements.",
    )

    assert result is True
    assert mock_bot.send_message.called
    call_kwargs = mock_bot.send_message.call_args[1]
    text = call_kwargs["text"]
    assert "Amazon" in text
    assert "Principal Systems Engineer" in text
    assert "88" in text

    # Verify Inline Keyboard Buttons
    reply_markup = call_kwargs.get("reply_markup")
    assert reply_markup is not None
    assert "inline_keyboard" in reply_markup
    buttons = reply_markup["inline_keyboard"][0]
    button_callbacks = [b.get("callback_data") for b in buttons]
    assert "apply:job_amzn_10" in button_callbacks
    assert "pdf:job_amzn_10" in button_callbacks
    assert "skip:job_amzn_10" in button_callbacks


def test_unconfigured_bot_graceful_degradation():
    """Test that notifier returns False gracefully when token or chat_id is missing."""
    notifier = TelegramNotifier(token=None, chat_id=None)
    # Should not throw any exception
    assert notifier.send_job_match("TestCo", "Engineer", 90, "https://test.com") is False
    assert notifier.send_captcha_alert("TestCo", "Engineer") is False
    assert notifier.send_review_gate("job_1", "TestCo", "Engineer", 90, "https://test.com") is False
    assert notifier.send_message("Test message") is False
    assert notifier.send_document("/tmp/doc.pdf") is False


def test_http_api_dispatch_success():
    """Test HTTP POST dispatch to Telegram Bot API when no bot_client is injected."""
    notifier = TelegramNotifier(token="test_token_123", chat_id="chat_456")
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 999}}

    with patch("src.interface.bot.telegram_bot.httpx.post", return_value=mock_resp) as mock_post:
        success = notifier.send_message("<b>Hello World</b>", reply_markup={"inline_keyboard": []})
        assert success is True
        assert mock_post.called
        args, kwargs = mock_post.call_args
        assert "https://api.telegram.org/bottest_token_123/sendMessage" in args[0]
        assert kwargs["json"]["chat_id"] == "chat_456"
        assert kwargs["json"]["text"] == "<b>Hello World</b>"
        assert kwargs["json"]["parse_mode"] == "HTML"


def test_http_api_dispatch_failure():
    """Test handling of HTTP error response from Telegram Bot API."""
    notifier = TelegramNotifier(token="test_token_123", chat_id="chat_456")
    
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request: chat not found"

    with patch("src.interface.bot.telegram_bot.httpx.post", return_value=mock_resp):
        success = notifier.send_message("Hello")
        assert success is False


def test_http_api_network_exception():
    """Test handling of network connection exception."""
    notifier = TelegramNotifier(token="test_token_123", chat_id="chat_456")

    with patch("src.interface.bot.telegram_bot.httpx.post", side_effect=Exception("Connection refused")):
        success = notifier.send_message("Hello")
        assert success is False


def test_send_document_mock_and_http(mock_bot):
    """Test document sending via bot client and HTTP endpoint."""
    notifier = TelegramNotifier(token="test_token", chat_id="12345", bot_client=mock_bot)
    assert notifier.send_document("/path/to/resume.pdf", caption="Resume PDF") is True
    assert mock_bot.send_document.called

    # Test HTTP path with mock
    notifier_http = TelegramNotifier(token="test_token", chat_id="12345")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("builtins.open", MagicMock()), patch("src.interface.bot.telegram_bot.httpx.post", return_value=mock_resp):
        assert notifier_http.send_document("/path/to/resume.pdf", caption="Resume PDF") is True


def test_command_status(mock_repos):
    """Test /status command returning pipeline statistics."""
    notifier = TelegramNotifier(
        token="token",
        chat_id="123",
        job_repo=mock_repos["job_repo"],
        app_repo=mock_repos["app_repo"],
    )

    response = notifier.handle_command("/status")
    assert "Pipeline Status" in response or "Status" in response
    assert "Jobs" in response or "Discovered" in response


def test_command_scan():
    """Test /scan command triggering job discovery."""
    mock_scanner = MagicMock()
    mock_scanner.scan_all.return_value = [
        JobPosting(id="j1", company="Target", title="Engineer", url="https://target.com")
    ]
    notifier = TelegramNotifier(token="token", chat_id="123", scanner=mock_scanner)

    response = notifier.handle_command("/scan")
    assert mock_scanner.scan_all.called
    assert "Scan completed" in response or "Discovered" in response or "1" in response


def test_command_apply(mock_repos):
    """Test /apply <id> and /apply with missing ID."""
    notifier = TelegramNotifier(token="token", chat_id="123", job_repo=mock_repos["job_repo"])

    # Test missing ID
    resp_missing = notifier.handle_command("/apply")
    assert "Please specify" in resp_missing or "Usage:" in resp_missing

    # Test valid ID
    resp_valid = notifier.handle_command("/apply job_c1_01")
    assert "Initiating 1-Click Apply" in resp_valid or "job_c1_01" in resp_valid
    assert mock_repos["job_repo"].update_status.called


def test_command_metrics():
    """Test /metrics command calculating conversion funnel metrics."""
    mock_funnel = MagicMock()
    mock_funnel.calculate_metrics.return_value.summary_markdown = "## Funnel Summary: 10 Applied, 2 Interviews"
    notifier = TelegramNotifier(token="token", chat_id="123", funnel_analytics=mock_funnel)

    response = notifier.handle_command("/metrics")
    assert "Funnel" in response or "Interviews" in response


def test_command_help_and_unknown():
    """Test unknown commands and /help return command list."""
    notifier = TelegramNotifier(token="token", chat_id="123")

    help_resp = notifier.handle_command("/help")
    assert "/status" in help_resp
    assert "/scan" in help_resp
    assert "/apply" in help_resp
    assert "/metrics" in help_resp

    unknown_resp = notifier.handle_command("/foobar")
    assert "/status" in unknown_resp


def test_callback_query_apply(mock_repos, mock_bot):
    """Test handling 1-click apply callback query."""
    notifier = TelegramNotifier(
        token="token",
        chat_id="123",
        job_repo=mock_repos["job_repo"],
        bot_client=mock_bot,
    )

    res = notifier.handle_callback_query("apply:job_c1_01", callback_query_id="cq_123")
    assert res["status"] == "ok"
    assert res["action"] == "apply"
    assert res["job_id"] == "job_c1_01"
    assert mock_repos["job_repo"].update_status.called
    assert mock_bot.answer_callback_query.called


def test_callback_query_skip(mock_repos, mock_bot):
    """Test handling skip callback query marking job as IGNORED."""
    notifier = TelegramNotifier(
        token="token",
        chat_id="123",
        job_repo=mock_repos["job_repo"],
        bot_client=mock_bot,
    )

    res = notifier.handle_callback_query("skip:job_c1_01", callback_query_id="cq_124")
    assert res["status"] == "ok"
    assert res["action"] == "skip"
    mock_repos["job_repo"].update_status.assert_called_with("job_c1_01", JobStatus.IGNORED)


def test_callback_query_pdf(mock_repos, mock_bot):
    """Test handling PDF callback query dispatching resume document."""
    notifier = TelegramNotifier(
        token="token",
        chat_id="123",
        artifact_repo=mock_repos["artifact_repo"],
        bot_client=mock_bot,
    )

    res = notifier.handle_callback_query("pdf:job_c1_01", callback_query_id="cq_125")
    assert res["status"] == "ok"
    assert res["action"] == "pdf"
    assert mock_bot.send_document.called


def test_process_update_message(mock_bot):
    """Test webhook update dispatcher with an incoming command message."""
    notifier = TelegramNotifier(token="token", chat_id="123", bot_client=mock_bot)
    update = {
        "update_id": 1,
        "message": {
            "chat": {"id": 123},
            "text": "/help",
        },
    }

    result = notifier.process_update(update)
    assert result is not None
    assert result["type"] == "message"
    assert mock_bot.send_message.called


def test_process_update_callback_query(mock_repos, mock_bot):
    """Test webhook update dispatcher with an incoming callback query."""
    notifier = TelegramNotifier(
        token="token",
        chat_id="123",
        job_repo=mock_repos["job_repo"],
        bot_client=mock_bot,
    )
    update = {
        "update_id": 2,
        "callback_query": {
            "id": "cbq_456",
            "from": {"id": 123},
            "message": {"chat": {"id": 123}},
            "data": "skip:job_c1_01",
        },
    }

    result = notifier.process_update(update)
    assert result is not None
    assert result["type"] == "callback_query"
    assert result["action"] == "skip"
