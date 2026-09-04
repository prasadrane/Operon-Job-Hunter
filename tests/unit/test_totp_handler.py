"""Unit tests for TOTPHandler - TOTP 2FA automation with Telegram SMS relay fallback."""

import importlib
import pytest
from unittest.mock import MagicMock, patch
import pyotp

from src.core.credentials.vault import CredentialVault, CredentialEntry

# Use importlib for numeric-prefixed module path
totp_handler_mod = importlib.import_module("src.pipeline.4_submission.totp_handler")
TOTPHandler = totp_handler_mod.TOTPHandler


class TestTOTPHandler:
    """Tests for TOTPHandler class."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_vault = MagicMock(spec=CredentialVault)
        self.handler = TOTPHandler(self.mock_vault)

    def test_get_totp_code_returns_valid_6_digit_code(self):
        """Test 1: get_totp_code returns valid 6-digit code when secret configured."""
        # Given: a valid TOTP secret in vault metadata
        totp_secret = "JBSWY3DPEHPK3PXP"  # Base32 encoded secret
        self.mock_vault.get_credentials.return_value = CredentialEntry(
            username="testuser",
            password="testpass",
            metadata={"totp_secret": totp_secret}
        )

        # When: get_totp_code called
        code = self.handler.get_totp_code("linkedin")

        # Then: returns 6-digit string
        assert code is not None
        assert len(code) == 6
        assert code.isdigit()

    def test_get_totp_code_returns_none_when_no_secret(self):
        """Test 2: get_totp_code returns None when no TOTP secret configured."""
        # Given: credentials without totp_secret metadata
        self.mock_vault.get_credentials.return_value = CredentialEntry(
            username="testuser",
            password="testpass",
            metadata={}
        )

        # When: get_totp_code called
        code = self.handler.get_totp_code("linkedin")

        # Then: returns None
        assert code is None

    def test_get_totp_code_matches_pyotp_expected(self):
        """Test 3: generated code matches pyotp expected value."""
        # Given: known secret and frozen time
        totp_secret = "JBSWY3DPEHPK3PXP"
        self.mock_vault.get_credentials.return_value = CredentialEntry(
            username="testuser",
            password="testpass",
            metadata={"totp_secret": totp_secret}
        )

        # When: get_totp_code called
        code = self.handler.get_totp_code("linkedin")

        # Then: matches pyotp generated code
        expected_totp = pyotp.TOTP(totp_secret)
        expected_code = expected_totp.now()
        assert code == expected_code

    def test_get_totp_code_returns_none_when_no_credentials(self):
        """Test: get_totp_code returns None when no credentials exist."""
        # Given: no credentials in vault
        self.mock_vault.get_credentials.return_value = None

        # When: get_totp_code called
        code = self.handler.get_totp_code("unknown_portal")

        # Then: returns None
        assert code is None

    def test_wait_for_sms_code_with_timeout(self):
        """Test: wait_for_sms_code returns None on timeout."""
        # Given: mock telegram handler that doesn't respond
        with patch.object(self.handler, '_telegram_hitl') as mock_telegram:
            mock_telegram.send_2fa_request.return_value = "msg_123"
            mock_telegram.wait_for_2fa_response.return_value = None

            # When: wait_for_sms_code called with short timeout
            code = self.handler.wait_for_sms_code("linkedin", timeout_sec=1)

            # Then: returns None
            assert code is None
            mock_telegram.send_2fa_request.assert_called_once()
            mock_telegram.wait_for_2fa_response.assert_called_once()

    def test_wait_for_sms_code_returns_user_reply(self):
        """Test: wait_for_sms_code returns code from user reply."""
        # Given: mock telegram handler with user response
        with patch.object(self.handler, '_telegram_hitl') as mock_telegram:
            mock_telegram.send_2fa_request.return_value = "msg_123"
            mock_telegram.wait_for_2fa_response.return_value = "456789"

            # When: wait_for_sms_code called
            code = self.handler.wait_for_sms_code("linkedin", timeout_sec=60)

            # Then: returns user's code
            assert code == "456789"
