"""Single construction seam for BrainInference (spec §6, Rev 4)."""
from __future__ import annotations

from typing import Optional

from src.brain.config import get_brain_settings
from src.brain.inference import BrainInference
from src.brain.ollama_client import OllamaClient


def get_brain(ollama_client: Optional[OllamaClient] = None) -> Optional[BrainInference]:
    """Return a ready BrainInference, or None when disabled / Ollama unavailable."""
    settings = get_brain_settings()
    if not settings.BRAIN_ENABLED:
        return None
    client = ollama_client or OllamaClient()
    if not client.is_available():
        return None
    return BrainInference(ollama_client=client)
