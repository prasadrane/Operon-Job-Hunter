"""Tests for prompt builder — Jinja2-based prompt construction per mode."""
import pytest

from src.brain.prompt_builder import build_prompt
from src.brain.mode_router import BrainMode
from src.brain.retriever import RetrievedChunk


@pytest.fixture
def sample_chunks():
    return [
        RetrievedChunk(id="story_1", content="Kafka governance story", score=0.95, chunk_type="story"),
        RetrievedChunk(id="skill_backend", content="Backend skills", score=0.88, chunk_type="skill_category"),
    ]


def test_build_avatar_prompt(sample_chunks):
    """Avatar prompt should be first-person and include Alex Rivera identity."""
    prompt = build_prompt("Tell me about Kafka", BrainMode.AVATAR, sample_chunks)
    assert "Alex Rivera" in prompt
    assert "Kafka governance story" in prompt
    assert "first person" in prompt.lower()


def test_build_avatar_prompt_includes_question(sample_chunks):
    """Avatar prompt should include the user's question."""
    prompt = build_prompt("Tell me about Kafka", BrainMode.AVATAR, sample_chunks)
    assert "Tell me about Kafka" in prompt


def test_build_tailoring_prompt(sample_chunks):
    """Tailoring prompt should include job description and tailoring instructions."""
    prompt = build_prompt(
        "Tailor for this job",
        BrainMode.TAILORING,
        sample_chunks,
        job_desc="Senior Backend Engineer, Kafka experience required",
    )
    assert "Senior Backend Engineer" in prompt
    assert "tailor" in prompt.lower()


def test_build_tailoring_prompt_without_job_desc(sample_chunks):
    """Tailoring prompt without job_desc should not crash."""
    prompt = build_prompt("Tailor my resume", BrainMode.TAILORING, sample_chunks)
    assert "tailor" in prompt.lower()


def test_build_qa_prompt(sample_chunks):
    """QA prompt should instruct factual answers with citations."""
    prompt = build_prompt("What metrics do you have?", BrainMode.QA, sample_chunks)
    assert "factual" in prompt.lower() or "cite" in prompt.lower()


def test_prompt_includes_retrieved_context(sample_chunks):
    """All prompts should wrap chunks in <retrieved_context> tags."""
    prompt = build_prompt("query", BrainMode.AVATAR, sample_chunks)
    assert "<retrieved_context>" in prompt
    assert "Kafka governance story" in prompt
    assert "</retrieved_context>" in prompt


def test_prompt_empty_chunks():
    """Prompt with no chunks should still render without errors."""
    prompt = build_prompt("hello", BrainMode.QA, [])
    assert "hello" in prompt
    assert "<retrieved_context>" in prompt


def test_prompt_chunk_type_label(sample_chunks):
    """Each chunk should show its type and id in the prompt."""
    prompt = build_prompt("q", BrainMode.AVATAR, sample_chunks)
    assert "[story: story_1]" in prompt
    assert "[skill_category: skill_backend]" in prompt


from src.brain.mode_router import BrainMode
from src.brain.prompt_builder import build_prompt
from src.brain.retriever import RetrievedChunk

CHUNKS = [RetrievedChunk(id="story_kafka_ci", content="Kafka governance work",
                         score=0.9, chunk_type="story")]


def test_tailoring_prompt_order_and_schema_block():
    p = build_prompt("tailor my resume", BrainMode.TAILORING, CHUNKS,
                     job_desc="Need Kafka expert", section="experience@rocket_mortgage")
    i_instr, i_schema, i_jd, i_ctx, i_query = (
        p.find("resume tailoring assistant"), p.find('"skills_to_emphasize"'),
        p.find("Need Kafka expert"), p.find("[story: story_kafka_ci]"),
        p.find("SECTION: experience@rocket_mortgage"))
    assert -1 not in (i_instr, i_schema, i_jd, i_ctx, i_query)
    assert i_instr < i_schema < i_jd < i_ctx < i_query


def test_tailoring_prompt_without_section_still_renders():
    p = build_prompt("q", BrainMode.TAILORING, CHUNKS, job_desc="JD text here")
    assert "JD text here" in p


def test_qa_prompt_unchanged_shape():
    p = build_prompt("what is X?", BrainMode.QA, CHUNKS)
    assert "[story: story_kafka_ci]" in p


def test_template_single_source_parity():
    """Serving and (future) synth read the same template file — P8."""
    from pathlib import Path
    tpl = Path("src/brain/prompts/tailor_resume.j2")
    assert tpl.exists()
    text = tpl.read_text(encoding="utf-8")
    assert "SECTION: {{ section }}" in text and "{{ schema_block }}" in text
