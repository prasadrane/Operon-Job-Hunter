"""Integration tests for CapSolver + CaptchaHandler flow."""

import importlib
import pytest
from unittest.mock import patch, MagicMock

ch_mod = importlib.import_module("src.pipeline.4_submission.captcha_handler")
CaptchaHandler = ch_mod.CaptchaHandler

cs_mod = importlib.import_module("src.pipeline.4_submission.capsolver_client")
CapSolverError = cs_mod.CapSolverError


class MockLocator:
    """Mock Playwright locator."""
    def __init__(self, count=0):
        self._count = count

    def count(self):
        return self._count


class MockPage:
    """Mock Playwright page."""
    def __init__(self, has_captcha=True, captcha_type="recaptcha"):
        self.has_captcha = has_captcha
        self.captcha_type = captcha_type

    def locator(self, selector):
        if self.has_captcha:
            if self.captcha_type == "recaptcha" and "recaptcha" in selector:
                return MockLocator(1)
            elif self.captcha_type == "hcaptcha" and "hcaptcha" in selector:
                return MockLocator(1)
            elif self.captcha_type == "turnstile" and "turnstile" in selector:
                return MockLocator(1)
        return MockLocator(0)

    def content(self):
        if self.has_captcha:
            return f"<html><body><div class='{self.captcha_type}'></div></body></html>"
        return "<html><body>No captcha</body></html>"


class TestCaptchaHandlerAutoSolve:
    """Test CaptchaHandler auto-solves when enabled + API key present."""

    def test_auto_solves_when_enabled_and_api_key_present(self):
        """CaptchaHandler auto-solves when enabled + API key present."""
        with patch.object(cs_mod.httpx.Client, 'post') as mock_post:
            # Mock CapSolver API response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "errorId": 0,
                "taskId": "task-123",
                "solution": {"token": "solved-token"},
                "status": "ready"
            }
            mock_post.return_value = mock_response

            page = MockPage(has_captcha=True, captcha_type="recaptcha")

            handler = CaptchaHandler(
                capsolver_api_key="test-key",
                captcha_auto_solve=True,
                capsolver_timeout_sec=10
            )

            # Detect captcha
            detected = handler.detect_captcha(page)
            assert detected is True

            # Solve should return token
            token = handler.handle_captcha(page, site_key="site-key", page_url="https://example.com")
            assert token == "solved-token"


class TestCaptchaHandlerHITLFallbackDisabled:
    """Test CaptchaHandler falls back to HITL when auto-solve disabled."""

    def test_falls_back_to_hitl_when_disabled(self):
        """CaptchaHandler falls back to HITL when auto-solve disabled."""
        page = MockPage(has_captcha=True, captcha_type="recaptcha")

        handler = CaptchaHandler(
            capsolver_api_key="test-key",
            captcha_auto_solve=False,
            timeout_sec=1
        )

        detected = handler.detect_captcha(page)
        assert detected is True

        # Should return None (HITL fallback) when auto-solve disabled
        token = handler.handle_captcha(page, site_key="site-key", page_url="https://example.com")
        assert token is None


class TestCaptchaHandlerHITLFallbackOnFailure:
    """Test CaptchaHandler falls back to HITL when CapSolver fails."""

    def test_falls_back_to_hitl_when_capsolver_fails(self):
        """CaptchaHandler falls back to HITL when CapSolver fails."""
        with patch.object(cs_mod.httpx.Client, 'post') as mock_post:
            # Mock CapSolver API error
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "errorId": 1,
                "errorCode": "ERROR_BALANCE_NOT_ENOUGH",
                "errorDescription": "Insufficient balance"
            }
            mock_post.return_value = mock_response

            page = MockPage(has_captcha=True, captcha_type="recaptcha")

            handler = CaptchaHandler(
                capsolver_api_key="test-key",
                captcha_auto_solve=True,
                capsolver_timeout_sec=5
            )

            detected = handler.detect_captcha(page)
            assert detected is True

            # Should return None (HITL fallback) when CapSolver fails
            token = handler.handle_captcha(page, site_key="site-key", page_url="https://example.com")
            assert token is None


class TestCaptchaHandlerHITLFallbackNoApiKey:
    """Test CaptchaHandler falls back to HITL when no API key."""

    def test_falls_back_to_hitl_when_no_api_key(self):
        """CaptchaHandler falls back to HITL when no API key."""
        page = MockPage(has_captcha=True, captcha_type="recaptcha")

        handler = CaptchaHandler(
            captcha_auto_solve=True,  # enabled but no key
            timeout_sec=1
        )

        detected = handler.detect_captcha(page)
        assert detected is True

        # Should return None (HITL fallback) when no API key
        token = handler.handle_captcha(page, site_key="site-key", page_url="https://example.com")
        assert token is None


class TestFullCaptchaFlow:
    """Integration: full flow from detection to solve."""

    def test_full_flow_detection_to_solve(self):
        """Full flow from detection to solve."""
        with patch.object(cs_mod.httpx.Client, 'post') as mock_post:
            # Mock successful CapSolver response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = [
                # Create task response
                {"errorId": 0, "taskId": "task-int-123"},
                # Get solution response
                {
                    "errorId": 0,
                    "taskId": "task-int-123",
                    "solution": {"token": "integration-token"},
                    "status": "ready"
                }
            ]
            mock_post.return_value = mock_response

            page = MockPage(has_captcha=True, captcha_type="recaptcha")

            handler = CaptchaHandler(
                capsolver_api_key="test-key",
                captcha_auto_solve=True,
                capsolver_timeout_sec=10
            )

            # Step 1: Detect captcha
            detected = handler.detect_captcha(page)
            assert detected is True, "Captcha should be detected"

            # Step 2: Solve captcha
            token = handler.handle_captcha(
                page,
                site_key="6Lc-test-key",
                page_url="https://example.com/apply"
            )
            assert token == "integration-token", "Should return solved token"

            # Verify API calls made
            assert mock_post.call_count == 2
