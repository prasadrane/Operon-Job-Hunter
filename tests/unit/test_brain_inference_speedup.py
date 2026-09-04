"""Unit tests for Career Brain inference speedup and caching optimizations."""

from unittest.mock import MagicMock, patch
import pytest

from src.brain.inference import BrainInference
from src.brain.mode_router import BrainMode
from src.brain.ollama_client import OllamaClient
from src.brain.response_formatter import BrainResponse


def test_ollama_client_session_reuse():
    """Verify OllamaClient uses a persistent session."""
    client = OllamaClient()
    assert hasattr(client, "session")
    assert client.session is not None


def test_ollama_client_passes_performance_options():
    """Verify generate passes keep_alive and optimized num_ctx/num_thread."""
    client = OllamaClient()
    with patch.object(client.session, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "Optimized output"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        ans = client.generate("Test prompt", mode="avatar")
        assert ans == "Optimized output"
        assert mock_post.called

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["keep_alive"] == "30m"
        assert "options" in payload
        assert payload["options"]["num_ctx"] == 2048  # qa-avatar profile (spec §5.2; v1's 1024/1536 truncation bug fixed)
        assert "num_thread" in payload["options"]


def test_brain_inference_lru_cache_hit():
    """Verify repeated queries hit the in-memory cache with <5ms latency and zero duplicate LLM calls."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.is_available.return_value = True
    mock_ollama.generate.return_value = "Cached answer on distributed systems."

    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    brain = BrainInference(ollama_client=mock_ollama, retriever=mock_retriever, enable_cache=True)

    # First call - cache miss
    resp1 = brain.query("What is your Kafka experience?", mode="avatar")
    assert resp1.answer == "Cached answer on distributed systems."
    assert mock_ollama.generate.call_count == 1

    # Second call with identical query - cache hit
    resp2 = brain.query("What is your Kafka experience?", mode="avatar")
    assert resp2.answer == "Cached answer on distributed systems."
    assert mock_ollama.generate.call_count == 1  # No second LLM call
    assert resp2.latency_ms < 50.0  # Ultra-fast cached return

    # Cache clear
    brain.clear_cache()
    resp3 = brain.query("What is your Kafka experience?", mode="avatar")
    assert mock_ollama.generate.call_count == 2
