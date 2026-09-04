"""Unit tests for Career Brain batch querying, streaming token generation, and SSE routes."""

import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from src.brain.api import create_brain_router
from src.brain.inference import BrainInference
from src.brain.retriever import RetrievedChunk
from src.brain.ollama_client import OllamaClient


def test_ollama_client_generate_stream_chunks():
    """Verify OllamaClient.generate_stream yields token chunks properly."""
    client = OllamaClient(base_url="http://localhost:11434")

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [
        json.dumps({"response": "Hello"}).encode("utf-8"),
        json.dumps({"response": " "}).encode("utf-8"),
        json.dumps({"response": "World!"}).encode("utf-8"),
    ]
    mock_response.status_code = 200

    with patch.object(client.session, "post", return_value=mock_response):
        tokens = list(client.generate_stream("Tell me about yourself"))
        assert tokens == ["Hello", " ", "World!"]


def test_ollama_client_hardware_tuning_num_gpu(monkeypatch):
    """Verify GPU auto-tuning sets num_gpu=99 when BRAIN_GPU_ENABLED=1."""
    monkeypatch.setenv("BRAIN_GPU_ENABLED", "1")
    client = OllamaClient(base_url="http://localhost:11434")
    opts = client._build_options(mode="avatar")
    assert opts.get("num_gpu") == 99


def test_brain_inference_batch_query_shares_retrieval():
    """Verify batch_query retrieves context chunks once and handles multiple queries."""
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [
        RetrievedChunk(id="exp_1", content="Led AWS platform scaling", score=0.95),
        RetrievedChunk(id="skill_1", content="Kafka microservices", score=0.92),
    ]

    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    mock_ollama.generate.side_effect = [
        "Answer 1: Scaled AWS to 10k RPS.",
        "Answer 2: Built Kafka event streams.",
    ]

    brain = BrainInference(ollama_client=mock_ollama, retriever=mock_retriever, enable_cache=True)
    queries = [
        "Describe your AWS experience.",
        "Describe your Kafka experience.",
    ]

    responses = brain.batch_query(queries, mode="qa")
    assert len(responses) == 2
    assert mock_retriever.retrieve.call_count == 1
    assert mock_ollama.generate.call_count == 2
    assert "AWS" in responses[0].answer
    assert "Kafka" in responses[1].answer


def test_brain_api_stream_endpoint():
    """Verify POST /brain/stream delivers SSE JSON event frames from query_stream."""
    from fastapi import FastAPI

    mock_brain = MagicMock()
    mock_brain.query_stream.return_value = iter([
        {"token": "Token1"}, {"token": " "}, {"token": "Token2"},
        {"response": {"answer": "Token1 Token2"}},
    ])

    app = FastAPI()
    app.include_router(create_brain_router(brain=mock_brain))
    client = TestClient(app)

    res = client.post("/brain/stream", json={"query": "Test query", "mode": "qa"})
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    content = res.text
    assert 'data: {"token": "Token1"}' in content
    assert 'data: {"token": "Token2"}' in content
    assert '"response"' in content
    assert "[DONE]" not in content  # framing is JSON events; no sentinel


import importlib, json
from unittest.mock import MagicMock

api_mod = importlib.import_module("src.brain.api")


def test_query_stream_yields_tokens_then_response():
    from src.brain.inference import BrainInference
    b = BrainInference.__new__(BrainInference)
    from src.brain.config import get_brain_settings
    b.settings = get_brain_settings()
    b._cache = {}
    b.retriever = MagicMock()
    b.retriever.retrieve.return_value = []
    b.ollama = MagicMock()
    b.ollama.is_available.return_value = True
    b.ollama.generate_stream.return_value = iter(["Hel", "lo"])
    events = list(b.query_stream("hi", mode="qa"))
    tokens = [e["token"] for e in events if "token" in e]
    final = [e for e in events if "response" in e]
    assert tokens == ["Hel", "lo"]
    assert len(final) == 1 and final[0]["response"]["answer"] == "Hello"


def test_stream_endpoint_sse_framing(monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    monkeypatch.setenv("BRAIN_ENABLED", "true")  # handler reads real settings, not brain.settings
    from src.brain.config import get_brain_settings
    get_brain_settings.cache_clear()
    brain = MagicMock()
    brain.query_stream.return_value = iter([{"token": "Hi"}, {"response": {"answer": "Hi"}}])
    app = FastAPI()
    app.include_router(api_mod.create_brain_router(brain))
    client = TestClient(app)
    r = client.post("/brain/stream", json={"query": "hello", "mode": "qa"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert 'data: {"token": "Hi"}' in body and body.count("data: ") == 2
