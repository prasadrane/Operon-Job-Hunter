"""Unit tests for Early-Applicant Recency Boost in Judge Minerva (RubricEvaluator)."""

from datetime import datetime, timezone, timedelta
import importlib
from unittest.mock import MagicMock, patch
import pytest

from src.core.models import JobPosting

_eval_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
RubricEvaluator = _eval_mod.RubricEvaluator


def test_rubric_evaluator_applies_10pt_boost_for_sub24h_job():
    """Verify jobs posted within 24 hours receive a +10 point recency boost."""
    evaluator = RubricEvaluator()
    now = datetime.now(timezone.utc)

    job_fresh = JobPosting(
        id="job_fresh_12h",
        company="Stripe",
        title="Senior Backend Infrastructure Engineer",
        url="https://stripe.com/jobs/1",
        description="Experience with AWS ECS, distributed systems, Kafka, and Python or C#.",
        posted_at=now - timedelta(hours=12),
        portal_type="greenhouse",
    )

    # Mock rule-based base score to be 80.0
    with patch.object(evaluator, "_evaluate_with_rules") as mock_rules:
        mock_eval = MagicMock()
        mock_eval.fit_score = 80.0
        mock_eval.block_scores = {"tech_stack": 25.0, "seniority": 20.0, "domain": 20.0, "compensation": 15.0}
        mock_eval.work_auth_blocker = False
        mock_eval.is_ghost_job = False
        mock_rules.return_value = mock_eval

        result = evaluator.evaluate(job_fresh)

    assert result.fit_score == 90.0  # 80.0 + 10.0 boost
    assert result.block_scores.get("recency_boost") == 10.0
    assert result.block_scores.get("posting_age_hours") is not None
    assert result.block_scores.get("posting_age_hours") < 24.0


def test_rubric_evaluator_applies_5pt_boost_for_sub72h_job():
    """Verify jobs posted within 72 hours receive a +5 point recency boost."""
    evaluator = RubricEvaluator()
    now = datetime.now(timezone.utc)

    job_recent = JobPosting(
        id="job_recent_48h",
        company="Databricks",
        title="Staff Platform Engineer",
        url="https://databricks.com/jobs/1",
        description="Experience with Kubernetes, AWS, Go, and Kafka.",
        posted_at=now - timedelta(hours=48),
        portal_type="greenhouse",
    )

    with patch.object(evaluator, "_evaluate_with_rules") as mock_rules:
        mock_eval = MagicMock()
        mock_eval.fit_score = 82.0
        mock_eval.block_scores = {"tech_stack": 25.0, "seniority": 20.0, "domain": 22.0, "compensation": 15.0}
        mock_eval.work_auth_blocker = False
        mock_eval.is_ghost_job = False
        mock_rules.return_value = mock_eval

        result = evaluator.evaluate(job_recent)

    assert result.fit_score == 87.0  # 82.0 + 5.0 boost
    assert result.block_scores.get("recency_boost") == 5.0


def test_rubric_evaluator_caps_fit_score_at_100():
    """Verify score does not exceed 100 with recency boost."""
    evaluator = RubricEvaluator()
    now = datetime.now(timezone.utc)

    job_perfect = JobPosting(
        id="job_perfect",
        company="OpenAI",
        title="Principal Software Engineer",
        url="https://openai.com/jobs/1",
        description="Distributed systems, Python, PyTorch, Kubernetes.",
        posted_at=now - timedelta(hours=2),
        portal_type="ashby",
    )

    with patch.object(evaluator, "_evaluate_with_rules") as mock_rules:
        mock_eval = MagicMock()
        mock_eval.fit_score = 96.0
        mock_eval.block_scores = {"tech_stack": 30.0, "seniority": 25.0, "domain": 25.0, "compensation": 16.0}
        mock_eval.work_auth_blocker = False
        mock_eval.is_ghost_job = False
        mock_rules.return_value = mock_eval

        result = evaluator.evaluate(job_perfect)

    assert result.fit_score == 100.0  # capped at 100


def test_rubric_evaluator_handles_missing_posted_at():
    """Verify jobs with no posted_at timestamp receive 0 recency boost gracefully."""
    evaluator = RubricEvaluator()

    job_no_date = JobPosting(
        id="job_no_date",
        company="Old Corp",
        title="Software Engineer",
        url="https://oldcorp.com/jobs/1",
        description="General software engineering requirements.",
        posted_at=None,
        portal_type="generic",
    )

    with patch.object(evaluator, "_evaluate_with_rules") as mock_rules:
        mock_eval = MagicMock()
        mock_eval.fit_score = 75.0
        mock_eval.block_scores = {"tech_stack": 20.0}
        mock_eval.work_auth_blocker = False
        mock_eval.is_ghost_job = False
        mock_rules.return_value = mock_eval

        result = evaluator.evaluate(job_no_date)

    assert result.fit_score == 75.0
    assert result.block_scores.get("recency_boost", 0.0) == 0.0
