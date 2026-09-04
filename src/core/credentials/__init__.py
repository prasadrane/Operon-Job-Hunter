"""CredentialVault — secure credential storage with OS keyring + env/file fallback.

Credentials are NEVER persisted to SQLite checkpoints or serialized to pipeline state.
"""

from src.core.credentials.vault import CredentialEntry, CredentialVault

__all__ = ["CredentialEntry", "CredentialVault"]
