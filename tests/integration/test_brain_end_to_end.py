"""End-to-end integration tests for the Career Brain inference pipeline.

Verifies that BrainInference correctly orchestrates mode routing, retrieval,
prompt building, inference, and response formatting across all three modes
(avatar, tailoring, qa).

Also validates that the BrainEvaluator can load the eval suite and compute
aggregate metrics.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.brain.retriever import RetrievedChunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_ollama() -> MagicMock:
    """Mock OllamaClient that always reports available and returns a canned answer."""
    client = MagicMock()
    client.is_available.return_value = True
    client.generate.return_value = (
        "I established enterprise-wide Kafka governance standards adopted by 5 teams."
    )
    return client


@pytest.fixture()
def mock_retriever() -> MagicMock:
    """Mock BrainRetriever returning a deterministic set of chunks."""
    retriever = MagicMock()
    retriever.retrieve.return_value = [
        RetrievedChunk(
            id="story_7",
            content="Kafka governance for 5 teams",
            score=0.95,
            chunk_type="story",
        ),
        RetrievedChunk(
            id="skill_kafka",
            content="Apache Kafka: event streaming, governance, schema registry",
            score=0.88,
            chunk_type="skill",
        ),
    ]
    return retriever


@pytest.fixture()
def brain(mock_ollama: MagicMock, mock_retriever: MagicMock):
    """A BrainInference instance wired to mock collaborators."""
    from src.brain.inference import BrainInference

    return BrainInference(ollama_client=mock_ollama, retriever=mock_retriever)


# ---------------------------------------------------------------------------
# End-to-end integration tests
# ---------------------------------------------------------------------------


def test_end_to_end_avatar_query(brain):
    """Avatar mode: story-driven query returns answer with citations."""
    response = brain.query("Tell me about your Kafka experience")

    assert response.answer != ""
    assert response.mode == "avatar"
    assert response.confidence > 0
    assert response.latency_ms >= 0  # Can be 0 with mocked components
    assert len(response.citations) > 0


def test_end_to_end_tailoring_query(brain):
    """Tailoring mode: job-description-aware query routes to tailoring."""
    response = brain.query(
        "Tailor my resume",
        mode="tailoring",
        job_desc="Senior Backend Engineer, Kafka experience required",
    )
    assert response.mode == "tailoring"
    assert response.answer != ""
    assert response.confidence > 0


def test_end_to_end_qa_query(brain):
    """QA mode: factual question returns a response in QA mode."""
    response = brain.query("What certifications do you hold?", mode="qa")
    assert response.mode == "qa"
    assert response.answer != ""


def test_end_to_end_auto_mode_routes(brain):
    """Auto mode: router picks the right mode based on query content."""
    response = brain.query("Describe a time you improved system reliability")
    assert response.mode in ("avatar", "tailoring", "qa")
    assert response.answer != ""


def test_end_to_end_empty_query_returns_empty_retrieval(mock_ollama):
    """Empty query does not crash; retriever returns empty chunks."""
    from src.brain.inference import BrainInference

    retriever = MagicMock()
    retriever.retrieve.return_value = []
    mock_ollama.generate.return_value = "No context available."

    brain = BrainInference(ollama_client=mock_ollama, retriever=retriever)
    response = brain.query("")

    # Should still produce a response (may fall through to Ollama with empty context)
    assert response.answer != ""
    assert response.latency_ms >= 0


# ---------------------------------------------------------------------------
# Eval suite & evaluator tests
# ---------------------------------------------------------------------------


EVAL_SUITE_PATH = Path("data/brain/eval_suite.json")


def test_eval_suite_loads():
    """The eval suite JSON is valid and contains 50 questions."""
    with open(EVAL_SUITE_PATH) as f:
        data = json.load(f)
    questions = data["questions"]
    assert len(questions) == 50
    # Every question has required fields
    for q in questions:
        assert "id" in q
        assert "query" in q
        assert "mode" in q


def test_eval_suite_modes_present():
    """The eval suite covers all three brain modes."""
    with open(EVAL_SUITE_PATH) as f:
        data = json.load(f)
    modes = {q["mode"] for q in data["questions"]}
    assert "avatar" in modes
    assert "tailoring" in modes
    assert "qa" in modes


def test_evaluator_loads_suite():
    """BrainEvaluator.load_eval_suite returns the question list."""
    from src.brain.evaluator import BrainEvaluator

    evaluator = BrainEvaluator.__new__(BrainEvaluator)
    questions = evaluator.load_eval_suite(EVAL_SUITE_PATH)
    assert len(questions) == 50
    assert all("id" in q for q in questions)


def test_evaluator_run_eval(mock_ollama, mock_retriever):
    """BrainEvaluator.run_exec computes aggregate metrics over the suite."""
    from src.brain.evaluator import BrainEvaluator
    from src.brain.inference import BrainInference

    brain = BrainInference(ollama_client=mock_ollama, retriever=mock_retriever)
    evaluator = BrainEvaluator(brain=brain)

    result = evaluator.run_eval(EVAL_SUITE_PATH)

    assert result["total_questions"] == 50
    assert result["avg_confidence"] > 0
    assert result["avg_latency_ms"] >= 0
    assert 0 <= result["warning_rate"] <= 1
    assert len(result["results"]) == 50
    # Each result has the expected keys
    for r in result["results"]:
        assert "id" in r
        assert "answer" in r
        assert "confidence" in r
        assert "latency_ms" in r


def test_evaluator_run_eval_with_limit(mock_ollama, mock_retriever):
    """BrainEvaluator.run_eval respects limit parameter."""
    from src.brain.evaluator import BrainEvaluator
    from src.brain.inference import BrainInference

    brain = BrainInference(ollama_client=mock_ollama, retriever=mock_retriever)
    evaluator = BrainEvaluator(brain=brain)

    result = evaluator.run_eval(EVAL_SUITE_PATH, limit=3)
    assert result["total_questions"] == 3
    assert len(result["results"]) == 3
