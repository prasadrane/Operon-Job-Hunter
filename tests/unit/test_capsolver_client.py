"""Unit tests for CapSolver client."""

import importlib
import pytest
from unittest.mock import patch, MagicMock

cs_mod = importlib.import_module("src.pipeline.4_submission.capsolver_client")
CapSolverClient = cs_mod.CapSolverClient
CapSolverError = cs_mod.CapSolverError
CapSolverTimeoutError = cs_mod.CapSolverTimeoutError


class TestCapSolverClientSolveRecaptcha:
    """Test solve_recaptcha returns token on success."""

    def test_solve_recaptcha_returns_token_on_success(self):
        """CapSolverClient.solve_recaptcha returns token on success."""
        with patch.object(cs_mod.httpx.Client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "errorId": 0,
                "taskId": "test-task-123",
                "solution": {"token": "recaptcha-token-abc"},
                "status": "ready"
            }
            mock_post.return_value = mock_response

            client = CapSolverClient(api_key="test-key", timeout_sec=30)
            token = client.solve_recaptcha(
                site_key="site-key-123",
                page_url="https://example.com"
            )

            assert token == "recaptcha-token-abc"
            assert mock_post.call_count == 2  # create task + get solution


class TestCapSolverClientApiErrors:
    """Test CapSolverClient handles API errors gracefully."""

    def test_handles_api_errors_gracefully(self):
        """CapSolverClient raises CapSolverError on API error."""
        with patch.object(cs_mod.httpx.Client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "errorId": 1,
                "errorCode": "ERROR_KEY_NOT_FOUND",
                "errorDescription": "API key not found"
            }
            mock_post.return_value = mock_response

            client = CapSolverClient(api_key="invalid-key", timeout_sec=30)

            with pytest.raises(CapSolverError, match="ERROR_KEY_NOT_FOUND"):
                client.solve_recaptcha(
                    site_key="site-key-123",
                    page_url="https://example.com"
                )


class TestCapSolverClientTimeout:
    """Test CapSolverClient times out after timeout_sec."""

    def test_times_out_after_timeout_sec(self):
        """CapSolverClient raises CapSolverTimeoutError when timeout exceeded."""
        with patch.object(cs_mod.httpx.Client, 'post') as mock_post, \
             patch.object(cs_mod.time, 'sleep'):
            # Always return "processing" status
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "errorId": 0,
                "taskId": "test-task-123",
                "status": "processing"
            }
            mock_post.return_value = mock_response

            client = CapSolverClient(api_key="test-key", timeout_sec=5)

            with pytest.raises(CapSolverTimeoutError, match="timed out"):
                client.solve_recaptcha(
                    site_key="site-key-123",
                    page_url="https://example.com"
                )

            # Should have polled multiple times before timing out
            assert mock_post.call_count >= 2


class TestCapSolverClientSolveHcaptcha:
    """Test solve_hcaptcha method."""

    def test_solve_hcaptcha_returns_token(self):
        """CapSolverClient.solve_hcaptcha returns token on success."""
        with patch.object(cs_mod.httpx.Client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "errorId": 0,
                "taskId": "test-task-456",
                "solution": {"token": "hcaptcha-token-xyz"},
                "status": "ready"
            }
            mock_post.return_value = mock_response

            client = CapSolverClient(api_key="test-key", timeout_sec=30)
            token = client.solve_hcaptcha(
                site_key="site-key-456",
                page_url="https://example.com"
            )

            assert token == "hcaptcha-token-xyz"


class TestCapSolverClientSolveTurnstile:
    """Test solve_turnstile method."""

    def test_solve_turnstile_returns_token(self):
        """CapSolverClient.solve_turnstile returns token on success."""
        with patch.object(cs_mod.httpx.Client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "errorId": 0,
                "taskId": "test-task-789",
                "solution": {"token": "turnstile-token-def"},
                "status": "ready"
            }
            mock_post.return_value = mock_response

            client = CapSolverClient(api_key="test-key", timeout_sec=30)
            token = client.solve_turnstile(
                site_key="site-key-789",
                page_url="https://example.com"
            )

            assert token == "turnstile-token-def"
