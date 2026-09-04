"""Unit tests for ATSOptimizer: Keyword coverage analysis, sweet spot scoring, and recommendations."""

import importlib
import pytest

ats_mod = importlib.import_module("src.pipeline.3_tailoring.ats_optimizer")
ATSOptimizer = ats_mod.ATSOptimizer
ATSDensityReport = ats_mod.ATSDensityReport


SAMPLE_JD = """
We are looking for a Senior Software Engineer to build high-throughput microservices.
Required Skills:
- 5+ years with C# or Python
- Distributed streaming architectures using Apache Kafka or AWS MSK
- Cloud infrastructure on AWS (ECS, Lambda, DynamoDB)
- Observability with Dynatrace, OpenTelemetry, or Splunk
- Experience with Docker, Kubernetes, and CI/CD pipelines
"""

SAMPLE_RESUME_TEXT = """
Senior Software Engineer with 10+ years experience building cloud-native systems.
- Architected event-driven pipelines using Apache Kafka and AWS MSK.
- Built microservices on AWS ECS Fargate, Lambda, and DynamoDB.
- Implemented observability with Dynatrace and OpenTelemetry.
- Deployed containers via Docker and GitHub Actions CI/CD.
"""


def test_extract_jd_requirements():
    """Verify ATS optimizer extracts core hard and infrastructure skills from JD."""
    optimizer = ATSOptimizer()
    reqs = optimizer.extract_requirements(SAMPLE_JD)
    
    assert "Kafka" in reqs or "Apache Kafka" in reqs
    assert "AWS" in reqs
    assert "Dynatrace" in reqs or "Observability" in reqs
    assert len(reqs) >= 4


def test_calculate_keyword_coverage_and_density():
    """Verify optimizer computes coverage ratio and identifies matched vs missing skills."""
    optimizer = ATSOptimizer()
    report = optimizer.analyze_density(resume_text=SAMPLE_RESUME_TEXT, jd_text=SAMPLE_JD)

    assert isinstance(report, ATSDensityReport)
    assert report.coverage_ratio >= 0.65  # High match
    assert "Kafka" in report.matched_keywords or "Apache Kafka" in report.matched_keywords
    assert report.is_in_sweet_spot is True


def test_low_coverage_triggers_optimization_recommendations():
    """Verify optimizer flags under-represented skills when coverage is below target threshold."""
    optimizer = ATSOptimizer()
    sparse_resume = "Software developer working on basic web pages with HTML and CSS."
    report = optimizer.analyze_density(resume_text=sparse_resume, jd_text=SAMPLE_JD)

    assert report.coverage_ratio < 0.40
    assert report.is_in_sweet_spot is False
    assert len(report.missing_keywords) > 0
    assert len(report.recommendations) > 0
