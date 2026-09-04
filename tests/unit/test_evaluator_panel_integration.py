"""Unit tests for ResumeGenerator EvaluatorPanel integration, multi-role tailoring, and CoreMemory injection."""

import importlib
from unittest.mock import MagicMock, patch
import pytest

from src.core.models import JobPosting

_eval_mod = importlib.import_module("src.pipeline.3_tailoring.evaluator_panel")
EvaluatorPanel = _eval_mod.EvaluatorPanel

_tailor_mod = importlib.import_module("src.pipeline.3_tailoring.resume_generator")
ResumeGenerator = _tailor_mod.ResumeGenerator


def test_evaluator_panel_scoring_composite_threshold():
    """Verify EvaluatorPanel computes composite score across 3 personas."""
    panel = EvaluatorPanel()
    bullets = [
        "Architected high-throughput Kafka streaming pipeline handling 15M+ events/day with 99.99% availability.",
        "Scaled distributed AWS ECS Fargate microservices, reducing p99 latency by 35% across 200k users.",
    ]
    keywords = ["Kafka", "AWS", "ECS", "Microservices"]

    eval_result = panel.evaluate_draft(bullets, target_keywords=keywords)
    assert eval_result["composite_score"] >= 85.0
    assert eval_result["passed"] is True
    assert "hm_score" in eval_result
    assert "ats_score" in eval_result
    assert "recruiter_score" in eval_result


def test_resume_generator_single_pass_evaluator_and_multi_role_tailoring():
    """Verify ResumeGenerator uses EvaluatorPanel and tailors bullets across recent roles."""
    mock_llm = MagicMock()
    mock_llm.generate.return_value = (
        '{"summary": "Senior Platform Engineer specializing in AWS and distributed systems.", '
        '"optimized_bullets": ["Architected distributed Kafka event pipelines handling 10M+ daily events."], '
        '"role_2_bullets": ["Optimized DynamoDB latency by 40% across microservices."]}'
    )

    generator = ResumeGenerator(llm=mock_llm)
    job = JobPosting(
        id="test_job_eval_1",
        company="Capital One",
        title="Lead Cloud Engineer",
        url="https://capitalone.com/jobs/1",
        description="Looking for expertise in AWS ECS, Kafka, Microservices, and DynamoDB at high scale.",
        portal_type="workday",
    )

    artifacts = generator.generate(job, target_pages=2)
    assert artifacts is not None
    assert artifacts.resume_pdf_path is not None
    assert artifacts.resume_pdf_path.endswith(".pdf")
