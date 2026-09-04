"""Integration tests for 2FA flow - TOTP auto-solve and SMS fallback."""

import importlib
import pytest
from unittest.mock import MagicMock, patch
import pyotp

from src.core.credentials.vault import CredentialVault, CredentialEntry

# Use importlib for numeric-prefixed module paths
totp_handler_mod = importlib.import_module("src.pipeline.4_submission.totp_handler")
TOTPHandler = totp_handler_mod.TOTPHandler

telegram_hitl_mod = importlib.import_module("src.interface.bot.telegram_hitl")
TelegramHITLManager = telegram_hitl_mod.TelegramHITLManager


class Test2FAFlowIntegration:
    """Integration tests for 2FA flow with TOTP and SMS fallback."""

    def test_send_2fa_request_sends_notification(self):
        """Test 4: TelegramHITLManager.send_2fa_request sends notification."""
        # Given: configured TelegramHITLManager
        with patch.object(TelegramHITLManager, '_ensure_table'):
            manager = TelegramHITLManager(db_path=":memory:")

            with patch.object(manager, '_send_telegram_message') as mock_send:
                mock_send.return_value = {"message_id": "msg_456"}

                # When: send_2fa_request called
                message_id = manager.send_2fa_request("linkedin", "job_123")

                # Then: telegram notification sent with 2FA request
                assert message_id == "msg_456"
                mock_send.assert_called_once()
                call_args = mock_send.call_args
                assert "2FA" in call_args[0][0] or "LinkedIn" in call_args[0][0]

    def test_wait_for_2fa_response_returns_user_reply(self):
        """Test 5: wait_for_2fa_response returns user reply."""
        # Given: configured TelegramHITLManager with pending response
        with patch.object(TelegramHITLManager, '_ensure_table'):
            manager = TelegramHITLManager(db_path=":memory:")
            manager._pending_2fa_requests = {"msg_789": {"portal": "linkedin", "job_id": "job_456"}}

            # Simulate user replying with code
            manager.submit_2fa_response("msg_789", "123456")

            # When: wait_for_2fa_response called
            code = manager.wait_for_2fa_response("msg_789", timeout_sec=2)

            # Then: returns user's code
            assert code == "123456"

    def test_totp_auto_solve_when_secret_available(self):
        """Test 6: Integration - TOTP auto-solve when secret available."""
        # Given: vault with TOTP secret
        mock_vault = MagicMock(spec=CredentialVault)
        totp_secret = "JBSWY3DPEHPK3PXP"
        mock_vault.get_credentials.return_value = CredentialEntry(
            username="testuser",
            password="testpass",
            metadata={"totp_secret": totp_secret}
        )

        handler = TOTPHandler(mock_vault)

        # When: get_totp_code called (simulating auto-solve)
        code = handler.get_totp_code("linkedin")

        # Then: valid 6-digit code returned without SMS fallback
        assert code is not None
        assert len(code) == 6
        assert code.isdigit()

        # Verify matches expected TOTP
        expected = pyotp.TOTP(totp_secret).now()
        assert code == expected

    def test_sms_fallback_when_totp_not_configured(self):
        """Test 7: Integration - SMS fallback when TOTP not configured."""
        # Given: vault without TOTP secret
        mock_vault = MagicMock(spec=CredentialVault)
        mock_vault.get_credentials.return_value = CredentialEntry(
            username="testuser",
            password="testpass",
            metadata={}  # No totp_secret
        )

        handler = TOTPHandler(mock_vault)

        # When: get_totp_code returns None, trigger SMS fallback
        code = handler.get_totp_code("linkedin")
        assert code is None

        # Then: SMS fallback path available
        with patch.object(handler, '_telegram_hitl') as mock_telegram:
            mock_telegram.send_2fa_request.return_value = "msg_fallback"
            mock_telegram.wait_for_2fa_response.return_value = "789012"

            sms_code = handler.wait_for_sms_code("linkedin", timeout_sec=30)
            assert sms_code == "789012"
            mock_telegram.send_2fa_request.assert_called_once()
