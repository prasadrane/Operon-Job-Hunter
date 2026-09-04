"""Tests for the get_brain() construction seam (Task 8)."""
from unittest.mock import MagicMock


def test_get_brain_returns_none_when_ollama_down(monkeypatch):
    from src.brain import factory
    fake_client = MagicMock()
    fake_client.is_available.return_value = False
    assert factory.get_brain(ollama_client=fake_client) is None


def test_get_brain_returns_brain_when_available(monkeypatch):
    from src.brain import factory
    fake_client = MagicMock()
    fake_client.is_available.return_value = True
    brain = factory.get_brain(ollama_client=fake_client)
    assert brain is not None and brain.ollama is fake_client


def test_get_brain_disabled(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "false")
    from src.brain.config import get_brain_settings
    get_brain_settings.cache_clear()
    from src.brain import factory
    assert factory.get_brain(ollama_client=MagicMock()) is None
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    get_brain_settings.cache_clear()
