import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.brain.synthesizer import Synthesizer, SynthesisReport


@pytest.fixture
def sample_jsonl(tmp_path):
    """Create a minimal JSONL file with one story chunk."""
    chunks = [
        {
            "type": "story",
            "id": "story_1",
            "content": "### Story 1 - Observability\n\n- Re-engineered Dynatrace monitoring, slashing alert noise by 80%.",
            "metadata": {"company": "Rocket Mortgage", "role": "Software Engineer"},
        },
        {
            "type": "skill_category",
            "id": "skill_languages",
            "content": "**Languages**: C#, Python, TypeScript",
            "metadata": {"category": "Languages", "items": ["C#", "Python", "TypeScript"]},
        },
    ]
    path = tmp_path / "test_resume.jsonl"
    with open(path, "w") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk) + "\n")
    return path


@pytest.fixture
def synthesizer():
    return Synthesizer(teacher_model="qwen-max")


def test_synthesizer_loads_jsonl(synthesizer, sample_jsonl):
    chunks = synthesizer.load_chunks(sample_jsonl)
    assert len(chunks) == 2
    assert chunks[0]["type"] == "story"
    assert chunks[1]["type"] == "skill_category"


async def test_synthesizer_generates_story_pairs(synthesizer, sample_jsonl):
    """Story chunks should generate Q&A pairs."""
    chunks = synthesizer.load_chunks(sample_jsonl)
    story_chunks = [c for c in chunks if c["type"] == "story"]
    assert len(story_chunks) == 1

    # Mock the LLM call
    with patch.object(synthesizer, "_call_teacher", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps({
            "question": "Tell me about your observability work.",
            "answer": "I re-engineered Dynatrace monitoring, reducing alert noise by 80%.",
        })
        pairs = await synthesizer.synthesize_chunk(story_chunks[0])
        assert len(pairs) >= 1
        assert pairs[0]["messages"][0]["role"] == "system"
        assert pairs[0]["messages"][1]["role"] == "user"
        assert pairs[0]["messages"][2]["role"] == "assistant"


def test_synthesizer_skips_graph_edges(synthesizer, tmp_path):
    """Graph edges should not generate training pairs directly."""
    chunks = [{"type": "graph_edge", "id": "edge_1", "content": "A -> B", "metadata": {}}]
    path = tmp_path / "edges.jsonl"
    with open(path, "w") as f:
        f.write(json.dumps(chunks[0]) + "\n")
    loaded = synthesizer.load_chunks(path)
    synthesizable = [c for c in loaded if synthesizer.is_synthesizable(c)]
    assert len(synthesizable) == 0


async def test_synthesis_report_structure(synthesizer, sample_jsonl):
    """Full synthesis should produce a valid report."""
    with patch.object(synthesizer, "_call_teacher", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps({
            "question": "Test question?",
            "answer": "Test answer.",
        })
        report = await synthesizer.synthesize_all(sample_jsonl, dry_run=True)
        assert isinstance(report, SynthesisReport)
        assert report.total_chunks >= 2


async def test_synthesizer_parses_markdown_json(synthesizer, sample_jsonl):
    """Synthesizer handles markdown-wrapped JSON."""
    chunks = synthesizer.load_chunks(sample_jsonl)
    story_chunks = [c for c in chunks if c["type"] == "story"]

    with patch.object(synthesizer, "_call_teacher", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '```json\n{"pairs": [{"question": "Q1?", "answer": "A1."}]}\n```'
        pairs = await synthesizer.synthesize_chunk(story_chunks[0])
        assert len(pairs) == 1
        assert pairs[0]["metadata"]["mode"] == "avatar"
        assert pairs[0]["messages"][1]["content"] == "Q1?"


async def test_synthesizer_parses_list_response(synthesizer, sample_jsonl):
    """Synthesizer handles direct list of pairs."""
    chunks = synthesizer.load_chunks(sample_jsonl)
    story_chunks = [c for c in chunks if c["type"] == "story"]

    with patch.object(synthesizer, "_call_teacher", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '[{"question": "Q2?", "answer": "A2."}]'
        pairs = await synthesizer.synthesize_chunk(story_chunks[0])
        assert len(pairs) == 1
        assert pairs[0]["metadata"]["mode"] == "avatar"


@pytest.mark.asyncio
async def test_call_teacher_retries_on_network_error_and_succeeds(monkeypatch):
    """_call_teacher retries transient network errors with backoff."""
    from requests.exceptions import ReadTimeout
    from src.brain.synthesizer import Synthesizer

    s = Synthesizer(teacher_model="qwen3.8-max")
    calls = []

    def mock_generate(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ReadTimeout("The read operation timed out")
        return "{\"result\": \"success\"}"

    mock_gw = MagicMock()
    mock_gw.alibaba_provider.generate = mock_generate
    monkeypatch.setattr("src.core.gateway.get_gateway", lambda: mock_gw)

    # Monkeypatch sleep to avoid slowing down tests
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    result = await s._call_teacher("test prompt", json_mode=True)
    assert result == "{\"result\": \"success\"}"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_call_teacher_exhausts_retries_and_raises(monkeypatch):
    """_call_teacher re-raises after exhausting max retries."""
    from requests.exceptions import ReadTimeout
    from src.brain.synthesizer import Synthesizer

    s = Synthesizer(teacher_model="qwen3.8-max")
    calls = []

    def mock_generate(*args, **kwargs):
        calls.append(1)
        raise ReadTimeout("The read operation timed out")

    mock_gw = MagicMock()
    mock_gw.alibaba_provider.generate = mock_generate
    monkeypatch.setattr("src.core.gateway.get_gateway", lambda: mock_gw)

    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    with pytest.raises(ReadTimeout):
        await s._call_teacher("test prompt", json_mode=True)

    assert len(calls) == 3  # default 3 attempts


