"""Model versioning and registry for Career Brain fine-tuned checkpoints."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path("data/brain/models.json")


class ModelRegistry:
    """Manage fine-tuned model versions stored as a JSON registry file."""

    def __init__(self, registry_path: Optional[Path] = None) -> None:
        self.registry_path = registry_path or REGISTRY_PATH

    def list_models(self) -> List[Dict[str, Any]]:
        """Return all registered models, or [] if the registry is missing."""
        if not self.registry_path.exists():
            return []
        try:
            with open(self.registry_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("models", [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read model registry at %s: %s", self.registry_path, exc)
            return []

    def get_active_model(self) -> Optional[Dict[str, Any]]:
        """Return the model marked ``active=True``, or the first model if none is active."""
        models = self.list_models()
        if not models:
            return None
        for m in models:
            if m.get("active"):
                return m
        return models[0]

    def _read_raw(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            return {}
        try:
            with open(self.registry_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read model registry at %s: %s", self.registry_path, exc)
            return {}

    def get_model_for_mode(self, mode: str) -> Optional[Dict[str, Any]]:
        """Resolve the model serving *mode*.

        Resolution order (spec §5.1 / P2):
        1. explicit active_modes pointer -> entry with that version
        2. entry with mode == *mode* and active=True
        3. mode-less active entry (legacy all-modes fallback)
        4. first mode-less entry
        """
        data = self._read_raw()
        models = data.get("models", [])
        if not models:
            return None
        pointer = (data.get("active_modes") or {}).get(mode)
        if pointer:
            for m in models:
                if m.get("version") == pointer:
                    return m
        for m in models:
            if m.get("mode") == mode and m.get("active"):
                return m
        for m in models:
            if "mode" not in m and m.get("active"):
                return m
        for m in models:
            if "mode" not in m:
                return m
        return None

    def set_active_for_mode(self, mode: str, version: str) -> None:
        """Point *mode* at *version*; raises ValueError if version unknown."""
        data = self._read_raw()
        models = data.get("models", [])
        if not any(m.get("version") == version for m in models):
            raise ValueError(f"Unknown model version: {version}")
        active_modes = data.get("active_modes") or {}
        active_modes[mode] = version
        data["active_modes"] = active_modes
        tmp = self.registry_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(self.registry_path)  # atomic flip; rollback is a pointer flip


_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Return the singleton :class:`ModelRegistry` instance."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
