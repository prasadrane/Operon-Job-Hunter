"""Tests for Brain inference orchestrator (Task 7)."""
import pytest
from unittest.mock import MagicMock, patch
from src.brain.inference import BrainInference, BrainResponse
from src.brain.mode_router import BrainMode


@pytest.fixture
def mock_ollama():
    client = MagicMock()
    client.is_available.return_value = True
    client.generate.return_value = (
        "I established Kafka governance for 5 teams, reducing schema conflicts by 80%."
    )
    return client


@pytest.fixture
def mock_retriever():
    retriever = MagicMock()
    from src.brain.retriever import RetrievedChunk
    retriever.retrieve.return_value = [
        RetrievedChunk(
            id="story_7",
            content="Kafka governance story",
            score=0.95,
            chunk_type="story",
        ),
    ]
    return retriever


@pytest.fixture
def brain(mock_ollama, mock_retriever):
    return BrainInference(ollama_client=mock_ollama, retriever=mock_retriever)


def test_query_returns_brain_response(brain):
    response = brain.query("Tell me about your Kafka experience")
    assert isinstance(response, BrainResponse)
    assert response.answer != ""
    assert response.mode in ("avatar", "tailoring", "qa")
    assert response.latency_ms >= 0


def test_query_avatar_mode(brain):
    response = brain.query("Tell me about your Kafka experience", mode="avatar")
    assert response.mode == "avatar"


def test_query_with_fallback(brain, mock_ollama):
    """When Ollama is unavailable, should fall back to cloud."""
    mock_ollama.is_available.return_value = False
    with patch.object(
        brain, "_cloud_fallback", return_value="Cloud response"
    ) as mock_fallback:
        response = brain.query("Tell me about Kafka")
        assert response.answer == "Cloud response"
        mock_fallback.assert_called_once()


def test_response_includes_citations(brain):
    response = brain.query("Tell me about Kafka")
    assert isinstance(response.citations, list)
    assert len(response.citations) >= 1
    # Each citation should have chunk_id and relevance
    for c in response.citations:
        assert hasattr(c, "chunk_id")
        assert hasattr(c, "relevance")


def test_response_confidence_range(brain):
    response = brain.query("Tell me about Kafka")
    assert 0.0 <= response.confidence <= 1.0


def test_response_to_dict(brain):
    response = brain.query("Tell me about Kafka")
    d = response.to_dict()
    assert "answer" in d
    assert "mode" in d
    assert "citations" in d
    assert "confidence" in d
    assert "latency_ms" in d


def test_query_unavailable_no_fallback(mock_ollama, mock_retriever):
    """When Ollama unavailable and fallback disabled, returns warning."""
    mock_ollama.is_available.return_value = False
    brain = BrainInference(ollama_client=mock_ollama, retriever=mock_retriever)
    # Override settings to disable fallback
    brain.settings = MagicMock()
    brain.settings.BRAIN_RETRIEVAL_TOP_K = 3
    brain.settings.BRAIN_FALLBACK_TO_CLOUD = False
    brain.settings.BRAIN_FACTGUARD_ENABLED = False
    response = brain.query("Tell me about Kafka")
    assert "unavailable" in response.answer.lower() or "warning" in str(
        response.warnings
    ).lower()


def test_strip_think_tags_removes_tags():
    from src.brain.response_formatter import strip_think_tags
    raw = "<think>\nThinking step 1...\nThinking step 2...\n</think>\n\nI have 10+ years experience."
    cleaned = strip_think_tags(raw)
    assert cleaned == "I have 10+ years experience."
    assert "<think>" not in cleaned
    assert "</think>" not in cleaned


def test_query_strips_think_tags_from_ollama(mock_ollama, mock_retriever):
    mock_ollama.generate.return_value = "<think>\nInternal reasoning\n</think>\nDirect answer."
    brain = BrainInference(ollama_client=mock_ollama, retriever=mock_retriever)
    response = brain.query("Tell me about Kafka")
    assert response.answer == "Direct answer."



def test_qa_generator_adapts_plan_json_to_prose():
    import importlib
    qa_gen = importlib.import_module("src.pipeline.3_tailoring.qa_generator")
    from src.brain.tailor_schema import TailorPlan
    plan = TailorPlan.model_validate({
        "section": "skills", "skills_to_emphasize": ["Kafka"],
        "stories": [], "bullets": [{"text": "Led Kafka governance", "source": "s1"}],
        "gaps": []})
    prose = qa_gen.adapt_brain_answer(plan.model_dump_json())
    assert "Led Kafka governance" in prose and "Kafka" in prose
    assert not prose.strip().startswith("{")
    # prose answers pass through untouched
    assert qa_gen.adapt_brain_answer("plain prose answer") == "plain prose answer"
