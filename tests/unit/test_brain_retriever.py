"""Tests for BrainRetriever — mode-specific retrieval wrapper."""
import pytest
from unittest.mock import MagicMock

from src.brain.retriever import BrainRetriever, RetrievedChunk
from src.brain.mode_router import BrainMode


@pytest.fixture
def mock_graph_retriever():
    retriever = MagicMock()
    retriever.retrieve_rrf.return_value = [
        {"id": "story_1", "content": "Story about Kafka", "score": 0.95},
        {"id": "skill_backend", "content": "Backend skills", "score": 0.88},
    ]
    return retriever


@pytest.fixture
def brain_retriever(mock_graph_retriever):
    return BrainRetriever(graph_retriever=mock_graph_retriever)


def test_retrieve_returns_retrieved_chunks(brain_retriever):
    """retrieve() should return a list of RetrievedChunk instances."""
    chunks = brain_retriever.retrieve("Tell me about Kafka", BrainMode.AVATAR, top_k=3)
    assert len(chunks) >= 1
    assert all(isinstance(c, RetrievedChunk) for c in chunks)


def test_retrieve_chunk_fields(brain_retriever):
    """Each RetrievedChunk should have correct fields from raw results."""
    chunks = brain_retriever.retrieve("Tell me about Kafka", BrainMode.AVATAR, top_k=3)
    assert chunks[0].id == "story_1"
    assert chunks[0].content == "Story about Kafka"
    assert chunks[0].score == 0.95


def test_retrieve_empty_query(brain_retriever):
    """Empty query should return empty list without calling retriever."""
    chunks = brain_retriever.retrieve("", BrainMode.QA, top_k=3)
    assert chunks == []
    assert not brain_retriever.graph_retriever.retrieve_rrf.called


def test_retrieve_tailoring_with_job_desc(mock_graph_retriever):
    """Tailoring mode with job_desc should trigger second retrieval call."""
    retriever = BrainRetriever(graph_retriever=mock_graph_retriever)
    retriever.retrieve("tailor resume", BrainMode.TAILORING, top_k=3, job_desc="Senior Engineer")
    # Should have been called twice: once for query, once for job_desc
    assert mock_graph_retriever.retrieve_rrf.call_count == 2


def test_retrieve_tailoring_deduplicates(mock_graph_retriever):
    """Tailoring mode should not duplicate chunks by id."""
    mock_graph_retriever.retrieve_rrf.return_value = [
        {"id": "story_1", "content": "Same story", "score": 0.9},
    ]
    retriever = BrainRetriever(graph_retriever=mock_graph_retriever)
    chunks = retriever.retrieve("tailor", BrainMode.TAILORING, top_k=3, job_desc="Engineer role")
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_retrieved_chunk_dataclass():
    """RetrievedChunk should be constructable with defaults."""
    chunk = RetrievedChunk(id="x", content="hello", score=0.5)
    assert chunk.chunk_type == "unknown"
    assert chunk.metadata == {}


def test_retrieved_chunk_with_metadata():
    """RetrievedChunk should accept custom metadata."""
    chunk = RetrievedChunk(id="x", content="hello", score=0.5, chunk_type="story", metadata={"source": "resume"})
    assert chunk.metadata == {"source": "resume"}
    assert chunk.chunk_type == "story"
