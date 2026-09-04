"""Tests for brain config."""
import pytest
from src.brain.config import BrainSettings, get_brain_settings


def test_brain_settings_defaults():
    settings = BrainSettings()
    assert settings.BRAIN_ENABLED is True
    assert settings.BRAIN_OLLAMA_URL == "http://localhost:11434"
    assert settings.BRAIN_OLLAMA_MODEL == "career-brain"
    assert settings.BRAIN_RETRIEVAL_TOP_K == 3
    assert settings.BRAIN_FACTGUARD_ENABLED is True
    assert settings.BRAIN_DEFAULT_MODE == "auto"
    assert settings.BRAIN_INFERENCE_TIMEOUT == 180
    assert settings.BRAIN_FALLBACK_TO_CLOUD is True


def test_brain_settings_env_override(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "false")
    monkeypatch.setenv("BRAIN_OLLAMA_MODEL", "custom-model")
    monkeypatch.setenv("BRAIN_RETRIEVAL_TOP_K", "5")
    settings = BrainSettings()
    assert settings.BRAIN_ENABLED is False
    assert settings.BRAIN_OLLAMA_MODEL == "custom-model"
    assert settings.BRAIN_RETRIEVAL_TOP_K == 5


def test_brain_settings_mode_validation():
    with pytest.raises(Exception):
        BrainSettings(BRAIN_DEFAULT_MODE="invalid_mode")


def test_phase1_settings_keys(monkeypatch):
    monkeypatch.setenv("BRAIN_TEACHER_MODEL", "qwen3.8-max")
    monkeypatch.setenv("BRAIN_CACHE_MAX_SIZE", "128")
    from src.brain.config import get_brain_settings
    get_brain_settings.cache_clear()
    s = get_brain_settings()
    assert s.BRAIN_TEACHER_MODEL == "qwen3.8-max"
    assert s.BRAIN_CACHE_MAX_SIZE == 128
    assert str(s.BRAIN_TELEMETRY_DIR).replace("\\", "/").endswith("data/brain/telemetry")
