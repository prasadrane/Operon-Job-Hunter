"""Unit tests for Stage 2 RubricEvaluator early knockouts and Stage 3 EvaluatorPanel optimization."""

import importlib
from unittest.mock import MagicMock
import pytest

from src.core.models import JobPosting

_rubric_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
RubricEvaluator = getattr(_rubric_mod, "RubricEvaluator")

_eval_panel_mod = importlib.import_module("src.pipeline.3_tailoring.evaluator_panel")
EvaluatorPanel = getattr(_eval_mod_panel := _eval_panel_mod, "EvaluatorPanel")


def test_rubric_evaluator_hard_knockout_short_circuits():
    """Verify that work authorization / clearance hard knockout immediately exits without LLM invocation."""
    mock_llm = MagicMock()
    evaluator = RubricEvaluator(llm=mock_llm)

    job = JobPosting(
        id="job_knockout_1",
        company="Defense Corp",
        title="Software Engineer - US Citizen Top Secret",
        description="Must hold active Top Secret / SCI clearance and US Citizenship. No sponsorship.",
        url="https://example.com/job1",
    )

    res = evaluator.evaluate(job)
    assert res.fit_score == 0.0
    assert res.work_auth_blocker is True
    assert "clearance" in res.reason.lower() or "authorization" in res.reason.lower()
    # LLM should never be called for hard knockout jobs
    mock_llm.generate.assert_not_called()


def test_evaluator_panel_optimized_scoring():
    """Verify EvaluatorPanel precompiled regex evaluation accurately scores quantified bullets."""
    panel = EvaluatorPanel()
    bullets = [
        "Architected distributed microservices reducing AWS cloud costs by 40% with 250ms latency.",
        "Built Kafka streaming data pipeline processing 10k messages per second with 99.99% uptime.",
    ]
    keywords = ["AWS", "Kafka", "Microservices"]

    eval_res = panel.evaluate_draft(bullets, target_keywords=keywords)
    assert eval_res["composite_score"] >= 85.0
    assert eval_res["passed"] is True
    assert eval_res["hm_score"] >= 90.0
    assert eval_res["ats_score"] >= 90.0
