"""Unit tests for CredentialVault core with OS keyring backend + env/file fallback."""

import json
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.credentials import CredentialEntry, CredentialVault


# ---------------------------------------------------------------------------
# 1. test_set_and_get_credentials_keyring
# ---------------------------------------------------------------------------
class TestSetAndGetKeyring:
    def test_set_and_get_credentials_keyring(self):
        """Stores and retrieves credentials via keyring backend."""
        mock_keyring = MagicMock()
        stored = {}

        def fake_set_pw(service, username, password):
            stored[(service, username)] = password

        def fake_get_pw(service, username):
            return stored.get((service, username))

        mock_keyring.set_password.side_effect = fake_set_pw
        mock_keyring.get_password.side_effect = fake_get_pw

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            vault = CredentialVault(backend="keyring", service_name="test_service")
            vault.set_credentials("greenhouse", "user@test.com", "s3cret")
            result = vault.get_credentials("greenhouse")

        assert result is not None
        assert result.username == "user@test.com"
        assert result.password == "s3cret"


# ---------------------------------------------------------------------------
# 2. test_get_credentials_not_found
# ---------------------------------------------------------------------------
class TestGetNotFound:
    def test_get_credentials_not_found(self):
        """Returns None when credentials don't exist."""
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            vault = CredentialVault(backend="keyring", service_name="test_service")
            result = vault.get_credentials("nonexistent_portal")

        assert result is None


# ---------------------------------------------------------------------------
# 3. test_delete_credentials
# ---------------------------------------------------------------------------
class TestDelete:
    def test_delete_credentials(self):
        """Removes entry from keyring."""
        mock_keyring = MagicMock()
        stored = {}

        def fake_set_pw(service, username, password):
            stored[(service, username)] = password

        def fake_get_pw(service, username):
            return stored.get((service, username))

        def fake_del_pw(service, username):
            stored.pop((service, username), None)

        mock_keyring.set_password.side_effect = fake_set_pw
        mock_keyring.get_password.side_effect = fake_get_pw
        mock_keyring.delete_password.side_effect = fake_del_pw

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            vault = CredentialVault(backend="keyring", service_name="test_service")
            vault.set_credentials("lever", "admin", "pw123")
            assert vault.get_credentials("lever") is not None

            deleted = vault.delete_credentials("lever")
            assert deleted is True
            assert vault.get_credentials("lever") is None


# ---------------------------------------------------------------------------
# 4. test_list_portals
# ---------------------------------------------------------------------------
class TestListPortals:
    def test_list_portals(self):
        """Returns portal names stored in keyring."""
        mock_keyring = MagicMock()

        # keyring doesn't natively support listing; our impl tracks portals
        # Simulate storing two portals
        stored = {}

        def fake_set_pw(service, username, password):
            stored[(service, username)] = password

        def fake_get_pw(service, username):
            return stored.get((service, username))

        mock_keyring.set_password.side_effect = fake_set_pw
        mock_keyring.get_password.side_effect = fake_get_pw

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            vault = CredentialVault(backend="keyring", service_name="test_service")
            vault.set_credentials("greenhouse", "u1", "p1")
            vault.set_credentials("lever", "u2", "p2")
            portals = vault.list_portals()

        assert "greenhouse" in portals
        assert "lever" in portals


# ---------------------------------------------------------------------------
# 5. test_env_backend_fallback
# ---------------------------------------------------------------------------
class TestEnvBackend:
    def test_env_backend_fallback(self):
        """Reads credentials from environment variables."""
        env_vars = {
            "CREDENTIALS_GREENHOUSE_USERNAME": "env_user",
            "CREDENTIALS_GREENHOUSE_PASSWORD": "env_pass",
            "CREDENTIALS_GREENHOUSE_EMAIL": "env@test.com",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            vault = CredentialVault(backend="env")
            result = vault.get_credentials("greenhouse")

        assert result is not None
        assert result.username == "env_user"
        assert result.password == "env_pass"
        assert result.metadata.get("email") == "env@test.com"


# ---------------------------------------------------------------------------
# 6. test_file_backend_dev
# ---------------------------------------------------------------------------
class TestFileBackend:
    def test_file_backend_dev(self):
        """Reads credentials from JSON file."""
        creds_data = {
            "workday": {
                "username": "file_user",
                "password": "file_pass",
                "metadata": {"department": "eng"},
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(creds_data, f)
            f.flush()
            tmppath = f.name

        try:
            vault = CredentialVault(backend="file", credentials_file=tmppath)
            result = vault.get_credentials("workday")
        finally:
            os.unlink(tmppath)

        assert result is not None
        assert result.username == "file_user"
        assert result.password == "file_pass"
        assert result.metadata.get("department") == "eng"


# ---------------------------------------------------------------------------
# 7. test_credential_entry_metadata
# ---------------------------------------------------------------------------
class TestMetadata:
    def test_credential_entry_metadata(self):
        """Metadata stored and retrieved correctly."""
        mock_keyring = MagicMock()
        stored = {}

        def fake_set_pw(service, username, password):
            stored[(service, username)] = password

        def fake_get_pw(service, username):
            return stored.get((service, username))

        mock_keyring.set_password.side_effect = fake_set_pw
        mock_keyring.get_password.side_effect = fake_get_pw

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            vault = CredentialVault(backend="keyring", service_name="test_service")
            meta = {"totp_secret": "JBSWY3DPEHPK3PXP", "email": "meta@test.com"}
            vault.set_credentials("ashby", "ashby_user", "ashby_pass", metadata=meta)
            result = vault.get_credentials("ashby")

        assert result is not None
        assert result.metadata["totp_secret"] == "JBSWY3DPEHPK3PXP"
        assert result.metadata["email"] == "meta@test.com"


# ---------------------------------------------------------------------------
# 8. test_keyring_unavailable_fallback
# ---------------------------------------------------------------------------
class TestKeyringFallback:
    def test_keyring_unavailable_fallback(self):
        """Gracefully falls back when keyring unavailable."""
        import sys

        # Simulate keyring raising an error on import
        with patch.dict(sys.modules, {"keyring": None}):
            env_vars = {
                "CREDENTIALS_FALLBACK_USERNAME": "fb_user",
                "CREDENTIALS_FALLBACK_PASSWORD": "fb_pass",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                vault = CredentialVault(backend="keyring")
                # Vault should auto-detect keyring failure and fall back to env
                result = vault.get_credentials("fallback")

        assert result is not None
        assert result.username == "fb_user"
        assert result.password == "fb_pass"


# ---------------------------------------------------------------------------
# 9. test_password_masked_in_logs
# ---------------------------------------------------------------------------
class TestLogMasking:
    def test_password_masked_in_logs(self, caplog):
        """No plaintext passwords in log output."""
        mock_keyring = MagicMock()
        stored = {}

        def fake_set_pw(service, username, password):
            stored[(service, username)] = password

        def fake_get_pw(service, username):
            return stored.get((service, username))

        mock_keyring.set_password.side_effect = fake_set_pw
        mock_keyring.get_password.side_effect = fake_get_pw

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            vault = CredentialVault(backend="keyring", service_name="test_service")
            vault.set_credentials("smartrecruiters", "sr_user", "super_secret_pw_123")

            with caplog.at_level(logging.DEBUG, logger="src.core.credentials"):
                vault.get_credentials("smartrecruiters")

        # Verify no plaintext password in any log record
        for record in caplog.records:
            assert "super_secret_pw_123" not in record.message
