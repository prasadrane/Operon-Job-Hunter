"""Tests for Career Brain API endpoints and ModelRegistry."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


@pytest.fixture
def mock_brain():
    """Mock BrainInference that returns a deterministic BrainResponse."""
    brain = MagicMock()
    from src.brain.response_formatter import BrainResponse, Citation

    brain.query.return_value = BrainResponse(
        answer="I led Kafka governance.",
        mode="avatar",
        citations=[Citation(chunk_id="story_7", relevance=0.95)],
        confidence=0.92,
        warnings=[],
        retrieved_chunks=3,
        latency_ms=42.0,
    )
    # Expose ollama stub for /status
    brain.ollama = MagicMock()
    brain.ollama.is_available.return_value = True
    brain.ollama.model = "career-brain"
    return brain


@pytest.fixture
def client(mock_brain):
    """FastAPI TestClient wired to a mock brain."""
    from src.brain.api import create_brain_router
    from fastapi import FastAPI

    app = FastAPI()
    router = create_brain_router(brain=mock_brain)
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# /brain/query
# ---------------------------------------------------------------------------


def test_query_endpoint(client, mock_brain):
    """POST /brain/query returns answer, mode, confidence."""
    response = client.post("/brain/query", json={"query": "Tell me about Kafka"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "I led Kafka governance."
    assert data["mode"] == "avatar"
    assert data["confidence"] == 0.92
    # Verify brain was called with expected args
    mock_brain.query.assert_called_once()
    call_kwargs = mock_brain.query.call_args
    assert call_kwargs.kwargs.get("query") == "Tell me about Kafka" or call_kwargs.args[0] == "Tell me about Kafka"


def test_query_with_mode(client, mock_brain):
    """POST /brain/query accepts explicit mode override."""
    response = client.post("/brain/query", json={"query": "anything", "mode": "qa"})
    assert response.status_code == 200


def test_query_validates_empty(client):
    """POST /brain/query rejects empty query strings."""
    response = client.post("/brain/query", json={"query": ""})
    assert response.status_code == 422


def test_query_validates_bad_mode(client):
    """POST /brain/query rejects invalid mode values."""
    response = client.post("/brain/query", json={"query": "hi", "mode": "bogus"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /brain/status
# ---------------------------------------------------------------------------


def test_status_endpoint(client):
    """GET /brain/status returns ollama_available flag."""
    response = client.get("/brain/status")
    assert response.status_code == 200
    data = response.json()
    assert "ollama_available" in data
    assert data["ollama_available"] is True
    assert data["model"] == "career-brain"


# ---------------------------------------------------------------------------
# /brain/models
# ---------------------------------------------------------------------------


def test_models_endpoint(client, tmp_path, monkeypatch):
    """GET /brain/models returns model list."""
    # Patch registry path to a temp file to avoid touching real data/
    registry_file = tmp_path / "models.json"
    registry_file.write_text(json.dumps({
        "models": [
            {"version": "v1", "model_name": "career-brain", "base_model": "qwen3-1.7b", "active": True}
        ]
    }))

    # Reset cached singleton so the monkeypatch takes effect
    import src.brain.model_registry as mr
    monkeypatch.setattr(mr, "REGISTRY_PATH", registry_file)
    monkeypatch.setattr(mr, "_registry", None)

    response = client.get("/brain/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) == 1
    assert data["models"][0]["version"] == "v1"


# ---------------------------------------------------------------------------
# ModelRegistry unit tests
# ---------------------------------------------------------------------------


def test_model_registry_list_empty(tmp_path):
    """ModelRegistry.list_models returns [] when file missing."""
    from src.brain.model_registry import ModelRegistry

    registry = ModelRegistry(registry_path=tmp_path / "nope.json")
    assert registry.list_models() == []


def test_model_registry_get_active(tmp_path):
    """ModelRegistry.get_active_model prefers active=True."""
    from src.brain.model_registry import ModelRegistry

    registry_file = tmp_path / "models.json"
    registry_file.write_text(json.dumps({
        "models": [
            {"version": "v0", "model_name": "old", "active": False},
            {"version": "v1", "model_name": "new", "active": True},
        ]
    }))
    registry = ModelRegistry(registry_path=registry_file)
    active = registry.get_active_model()
    assert active is not None
    assert active["version"] == "v1"


def test_model_registry_get_active_falls_back_to_first(tmp_path):
    """ModelRegistry.get_active_model returns first model when none active."""
    from src.brain.model_registry import ModelRegistry

    registry_file = tmp_path / "models.json"
    registry_file.write_text(json.dumps({
        "models": [
            {"version": "v0", "model_name": "only"},
        ]
    }))
    registry = ModelRegistry(registry_path=registry_file)
    active = registry.get_active_model()
    assert active is not None
    assert active["version"] == "v0"


def test_model_registry_get_active_none(tmp_path):
    """ModelRegistry.get_active_model returns None when no models."""
    from src.brain.model_registry import ModelRegistry

    registry = ModelRegistry(registry_path=tmp_path / "missing.json")
    assert registry.get_active_model() is None
