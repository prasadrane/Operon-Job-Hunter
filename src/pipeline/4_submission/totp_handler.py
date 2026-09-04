"""TOTP 2FA automation with Telegram SMS relay fallback.

Handles two-factor authentication for job portals:
1. Auto-solve via TOTP when secret configured in CredentialVault metadata
2. SMS fallback via Telegram HITL when TOTP not available
"""

import logging
import re
from typing import Any, Optional

import pyotp

logger = logging.getLogger(__name__)


class TOTPHandler:
    """Handles TOTP-based 2FA with Telegram SMS relay fallback.

    TOTP secrets are stored in CredentialEntry.metadata["totp_secret"]
    (base32-encoded). When no secret is available, falls back to requesting
    SMS code via Telegram notification.
    """

    def __init__(self, credential_vault: Any) -> None:
        """Initialize TOTPHandler.

        Args:
            credential_vault: CredentialVault instance for fetching TOTP secrets
        """
        self._vault = credential_vault
        self._telegram_hitl = self._init_telegram_hitl()

    def _init_telegram_hitl(self) -> Any:
        """Lazy-init TelegramHITLManager. Returns None if not configured."""
        try:
            from src.interface.bot.telegram_hitl import TelegramHITLManager
            return TelegramHITLManager()
        except Exception as exc:
            logger.debug("TelegramHITLManager not available: %s", exc)
            return None

    def get_totp_code(self, portal_type: str) -> Optional[str]:
        """Fetch TOTP secret from vault and generate current 6-digit code.

        Args:
            portal_type: Portal identifier (e.g. "linkedin", "indeed")

        Returns:
            6-digit TOTP code string, or None if no secret configured
        """
        portal_key = portal_type.lower().strip()

        credentials = self._vault.get_credentials(portal_key)
        if credentials is None:
            logger.debug("No credentials found for portal=%s", portal_key)
            return None

        totp_secret = credentials.metadata.get("totp_secret")
        if not totp_secret:
            logger.debug("No totp_secret in metadata for portal=%s", portal_key)
            return None

        try:
            totp = pyotp.TOTP(totp_secret)
            code = totp.now()
            logger.info("Generated TOTP code for portal=%s", portal_key)
            return code
        except Exception as exc:
            logger.error("Failed to generate TOTP for portal=%s: %s", portal_key, exc)
            return None

    def wait_for_sms_code(self, portal_type: str, timeout_sec: int = 60) -> Optional[str]:
        """Send Telegram notification requesting SMS code and wait for user reply.

        Args:
            portal_type: Portal identifier for 2FA request
            timeout_sec: How long to wait for user response (default 60s)

        Returns:
            SMS code entered by user, or None on timeout/no telegram
        """
        if self._telegram_hitl is None:
            logger.warning("TelegramHITLManager not available for SMS fallback")
            return None

        portal_key = portal_type.lower().strip()

        try:
            message_id = self._telegram_hitl.send_2fa_request(portal_key, job_id="")
            if not message_id:
                logger.warning("Failed to send 2FA request via Telegram")
                return None

            code = self._telegram_hitl.wait_for_2fa_response(
                message_id=message_id,
                timeout_sec=timeout_sec,
            )
            return code
        except Exception as exc:
            logger.error("SMS fallback failed for portal=%s: %s", portal_key, exc)
            return None
