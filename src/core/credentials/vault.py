"""CredentialVault core implementation with 3 backends: keyring, env, file."""

import importlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class CredentialEntry:
    """A single credential set for a portal."""

    username: str
    password: str
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"username": self.username, "password": self.password, "metadata": self.metadata})

    @classmethod
    def from_json(cls, raw: str) -> "CredentialEntry":
        d = json.loads(raw)
        return cls(username=d["username"], password=d["password"], metadata=d.get("metadata", {}))

    def __repr__(self) -> str:
        return f"CredentialEntry(username={self.username!r}, password=***MASKED***, metadata_keys={list(self.metadata.keys())})"


# ── Vault ─────────────────────────────────────────────────────────────────────

_DEFAULT_SERVICE = "careergraph"
_DEFAULT_FILE = "./data/credentials.json"


class CredentialVault:
    """Secure credential storage.

    Backends (in priority order):
      1. keyring — OS-native credential store (default)
      2. env     — CREDENTIALS_{PORTAL}_{USERNAME|PASSWORD|...} env vars
      3. file    — JSON file at data/credentials.json (dev only)

    If keyring is unavailable at runtime, the vault silently falls back to env,
    then file.  Credentials are fetched on-demand and NEVER cached in memory or
    serialized to pipeline state.
    """

    def __init__(
        self,
        backend: Optional[str] = None,
        service_name: str = _DEFAULT_SERVICE,
        credentials_file: Optional[str] = None,
    ):
        self._service_name = service_name
        self._credentials_file = credentials_file or _DEFAULT_FILE
        self._known_portals: set[str] = set()

        # Resolve backend: explicit param > config setting > default
        if backend is None:
            backend = self._read_backend_from_config()
        self._requested_backend = backend

        # Track which portals are stored so list_portals() works for keyring
        # (keyring has no native listing API)
        self._portal_store: set[str] = set()

        # Attempt to initialise the keyring backend; fall back on failure
        self._keyring_mod = None
        self._active_backend = self._resolve_backend(backend)

    # ── public API ────────────────────────────────────────────────────────

    def get_credentials(self, portal_type: str) -> Optional[CredentialEntry]:
        """Fetch credentials for *portal_type*. Returns None if not found."""
        portal_key = portal_type.lower().strip()
        logger.debug("get_credentials portal=%s backend=%s", portal_key, self._active_backend)

        if self._active_backend == "keyring" and self._keyring_mod is not None:
            return self._get_keyring(portal_key)
        if self._active_backend == "env":
            return self._get_env(portal_key)
        if self._active_backend == "file":
            return self._get_file(portal_key)
        return None

    def set_credentials(
        self,
        portal_type: str,
        username: str,
        password: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """Store credentials for *portal_type*."""
        portal_key = portal_type.lower().strip()
        entry = CredentialEntry(username=username, password=password, metadata=metadata or {})
        logger.debug("set_credentials portal=%s username=%s", portal_key, username)

        if self._active_backend == "keyring" and self._keyring_mod is not None:
            self._keyring_mod.set_password(self._service_name, portal_key, entry.to_json())
        self._portal_store.add(portal_key)

    def delete_credentials(self, portal_type: str) -> bool:
        """Delete credentials for *portal_type*. Returns True if removed."""
        portal_key = portal_type.lower().strip()
        logger.debug("delete_credentials portal=%s", portal_key)

        if self._active_backend == "keyring" and self._keyring_mod is not None:
            try:
                self._keyring_mod.delete_password(self._service_name, portal_key)
                self._portal_store.discard(portal_key)
                return True
            except Exception:
                logger.debug("delete_credentials keyring raised; returning False")
                return False
        return False

    def list_portals(self) -> list[str]:
        """Return known portal names."""
        return sorted(self._portal_store)

    @property
    def active_backend(self) -> str:
        return self._active_backend

    # ── backend resolution ────────────────────────────────────────────────

    @staticmethod
    def _read_backend_from_config() -> str:
        try:
            from src.core.config import get_settings

            settings = get_settings()
            return getattr(settings, "credential_backend", "keyring")
        except Exception:
            return "keyring"

    def _resolve_backend(self, requested: str) -> str:
        """Try to initialise the requested backend; fall back gracefully."""
        if requested == "keyring":
            try:
                mod = importlib.import_module("keyring")
                # Probe — some installs raise on first use (no D-Bus, etc.)
                mod.get_password("__careergraph_probe__", "__probe__")
                self._keyring_mod = mod
                logger.debug("keyring backend initialised")
                return "keyring"
            except Exception as exc:
                logger.warning("keyring unavailable (%s); falling back to env", exc)

        if requested in ("keyring", "env"):
            return "env"

        if requested == "file":
            return "file"

        logger.warning("unknown backend %r; defaulting to env", requested)
        return "env"

    # ── keyring helpers ───────────────────────────────────────────────────

    def _get_keyring(self, portal_key: str) -> Optional[CredentialEntry]:
        raw = self._keyring_mod.get_password(self._service_name, portal_key)
        if raw is None:
            return None
        try:
            entry = CredentialEntry.from_json(raw)
            self._portal_store.add(portal_key)
            return entry
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("corrupt keyring entry for %s: %s", portal_key, exc)
            return None

    # ── env helpers ───────────────────────────────────────────────────────

    def _get_env(self, portal_key: str) -> Optional[CredentialEntry]:
        prefix = f"CREDENTIALS_{portal_key.upper()}_"
        username = os.environ.get(f"{prefix}USERNAME")
        password = os.environ.get(f"{prefix}PASSWORD")
        if username is None or password is None:
            return None

        metadata: Dict[str, str] = {}
        skip = {"USERNAME", "PASSWORD"}
        for key, val in os.environ.items():
            if key.startswith(prefix):
                field_name = key[len(prefix):]
                if field_name not in skip:
                    metadata[field_name.lower()] = val
        self._portal_store.add(portal_key)
        return CredentialEntry(username=username, password=password, metadata=metadata)

    # ── file helpers ──────────────────────────────────────────────────────

    def _get_file(self, portal_key: str) -> Optional[CredentialEntry]:
        path = Path(self._credentials_file)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("cannot read credentials file %s: %s", path, exc)
            return None

        entry_data = data.get(portal_key)
        if not entry_data:
            return None
        self._portal_store.add(portal_key)
        return CredentialEntry(
            username=entry_data["username"],
            password=entry_data["password"],
            metadata=entry_data.get("metadata", {}),
        )
