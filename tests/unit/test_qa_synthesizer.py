"""Unit tests for QASynthesizer: Deterministic triage, STAR+R retrieval, and FactGuard validation."""

import importlib
import pytest

from src.core.models import CandidateProfile

qa_mod = importlib.import_module("src.pipeline.4_submission.qa_synthesizer")
QASynthesizer = qa_mod.QASynthesizer
QuestionType = qa_mod.QuestionType


@pytest.fixture
def sample_profile():
    return {
        "first_name": "Alex",
        "last_name": "Rivera",
        "email": "alex.rivera@example.com",
        "phone": "+1 (555) 234-5678",
        "us_work_authorized": True,
        "requires_sponsorship": True,
        "location": "Chicago, IL",
        "master_stories": [
            {
                "title": "Spark Query Optimization",
                "situation": "Enterprise streaming pipelines suffered 40% memory spillover during peak load.",
                "task": "Optimize partition strategy and cache management.",
                "action": "Redesigned broadcast joins and tuned executor memory allocation.",
                "result": "Reduced pipeline latency by 35% and eliminated executor OOMs.",
                "reflection": "Early memory profiling prevents downstream distributed bottlenecking.",
                "skills": ["Apache Spark", "Kafka", "Python", "Distributed Systems"]
            }
        ]
    }


def test_question_triage_deterministic_vs_custom(sample_profile):
    """Verify triage separates deterministic profile/EEO questions from custom essays."""
    synth = QASynthesizer()
    
    # 1. Deterministic profile fields
    q1 = synth.triage_question("What is your legal first name?")
    assert q1.question_type == QuestionType.PROFILE_FIELD
    assert q1.is_custom is False
    assert synth.resolve_answer("What is your legal first name?", sample_profile) == "Alex"

    # 2. Deterministic sponsorship
    q2 = synth.triage_question("Will you now or in the future require visa sponsorship?")
    assert q2.question_type == QuestionType.WORK_AUTH_SPONSORSHIP
    assert q2.is_custom is False
    assert synth.resolve_answer("Will you now or in the future require visa sponsorship?", sample_profile) == "Yes"

    # 3. Deterministic EEO
    q3 = synth.triage_question("Gender / Demographic Self-Identification Survey")
    assert q3.question_type == QuestionType.EEO_DEMOGRAPHIC
    assert q3.is_custom is False
    assert synth.resolve_answer("Gender / Demographic Self-Identification Survey", sample_profile) == "Decline to Self-Identify"

    # 4. Custom open-ended essay
    q4 = synth.triage_question("Why do you want to join our data infrastructure team?")
    assert q4.question_type == QuestionType.CUSTOM_ESSAY
    assert q4.is_custom is True


def test_custom_question_synthesis_with_starr_retrieval(sample_profile):
    """Verify custom essay prompts retrieve relevant STAR+R story evidence and generate grounded responses."""
    synth = QASynthesizer()
    prompt = "Describe a time you optimized a distributed data processing system."
    
    answer = synth.resolve_answer(prompt, sample_profile, max_chars=300)
    assert len(answer) <= 300
    assert "Spark" in answer or "latency" in answer or "memory" in answer


def test_character_limit_enforcement(sample_profile):
    """Verify strict length limit truncation and cleanly formatted output."""
    synth = QASynthesizer()
    prompt = "Why are you a good fit for this role?"
    
    answer_short = synth.resolve_answer(prompt, sample_profile, max_chars=120)
    assert len(answer_short) <= 120
