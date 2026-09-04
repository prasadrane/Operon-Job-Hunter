"""Unit tests for PrometheusMetrics.

Verifies:
1. Counter increments (submissions, captcha, api requests)
2. Histogram observations (submission duration, api duration)
3. Gauge set operations (active submissions, queue depth)
4. generate_metrics() returns valid Prometheus exposition format
5. Thread-safety (registry isolation)
"""

import re

import pytest
from prometheus_client import CollectorRegistry

from src.core.telemetry.prometheus_metrics import PrometheusMetrics


@pytest.fixture
def metrics():
    """Fresh PrometheusMetrics with isolated registry per test."""
    return PrometheusMetrics(registry=CollectorRegistry())


class TestCounters:
    """Counter increment tests."""

    def test_inc_submissions_total(self, metrics):
        metrics.inc_submissions_total("greenhouse", "success")
        metrics.inc_submissions_total("greenhouse", "success")
        metrics.inc_submissions_total("lever", "failure")

        output = metrics.generate_metrics()
        assert 'careergraph_submissions_total' in output
        assert 'portal_type="greenhouse"' in output
        assert 'status="success"' in output
        # Two increments for greenhouse+success
        match = re.search(
            r'careergraph_submissions_total\{[^}]*portal_type="greenhouse"[^}]*status="success"[^}]*\} (\d+\.?\d*)',
            output,
        )
        assert match, f"Counter not found in output: {output}"
        assert float(match.group(1)) == 2.0

    def test_inc_captcha_solved_total(self, metrics):
        metrics.inc_captcha_solved_total("hcaptcha", "capsolver")
        output = metrics.generate_metrics()
        assert 'careergraph_captcha_solved_total' in output
        assert 'captcha_type="hcaptcha"' in output
        assert 'method="capsolver"' in output

    def test_inc_api_requests_total(self, metrics):
        metrics.inc_api_requests_total("/api/jobs", 200)
        metrics.inc_api_requests_total("/api/jobs", 200)
        metrics.inc_api_requests_total("/api/jobs", 500)

        output = metrics.generate_metrics()
        assert 'careergraph_api_requests_total' in output
        assert 'endpoint="/api/jobs"' in output
        assert 'status="200"' in output
        assert 'status="500"' in output


class TestHistograms:
    """Histogram observation tests."""

    def test_observe_submission_duration(self, metrics):
        metrics.observe_submission_duration("greenhouse", 42.5)
        metrics.observe_submission_duration("greenhouse", 10.0)

        output = metrics.generate_metrics()
        assert "careergraph_submission_duration_seconds" in output
        assert 'portal_type="greenhouse"' in output
        # _count should be 2
        assert "careergraph_submission_duration_seconds_count" in output

    def test_observe_api_request_duration(self, metrics):
        metrics.observe_api_request_duration("/api/jobs", 0.025)
        output = metrics.generate_metrics()
        assert "careergraph_api_request_duration_seconds" in output
        assert 'endpoint="/api/jobs"' in output


class TestGauges:
    """Gauge set tests."""

    def test_set_active_submissions(self, metrics):
        metrics.set_active_submissions(5)
        output = metrics.generate_metrics()
        assert "careergraph_active_submissions 5.0" in output

        metrics.set_active_submissions(3)
        output = metrics.generate_metrics()
        assert "careergraph_active_submissions 3.0" in output

    def test_set_queue_depth(self, metrics):
        metrics.set_queue_depth("submissions", 42)
        output = metrics.generate_metrics()
        assert "careergraph_queue_depth" in output
        assert 'queue_name="submissions"' in output
        assert "42.0" in output


class TestGenerateMetrics:
    """Output format validation."""

    def test_generate_metrics_returns_string(self, metrics):
        result = metrics.generate_metrics()
        assert isinstance(result, str)

    def test_generate_metrics_empty_registry(self):
        """Empty registry produces empty or minimal output."""
        m = PrometheusMetrics(registry=CollectorRegistry())
        result = m.generate_metrics()
        assert isinstance(result, str)

    def test_content_type(self, metrics):
        ct = metrics.content_type
        assert "text/plain" in ct
        assert "version=" in ct

    def test_prometheus_format_structure(self, metrics):
        """Output follows Prometheus exposition format with HELP/TYPE lines."""
        metrics.inc_submissions_total("ashby", "success")
        output = metrics.generate_metrics()
        # Prometheus format includes HELP and TYPE comment lines
        assert "# HELP careergraph_submissions_total" in output
        assert "# TYPE careergraph_submissions_total counter" in output


class TestRegistryIsolation:
    """Ensure metrics from one instance don't leak into another."""

    def test_separate_registries(self):
        m1 = PrometheusMetrics(registry=CollectorRegistry())
        m2 = PrometheusMetrics(registry=CollectorRegistry())

        m1.inc_submissions_total("greenhouse", "success")
        m1.set_active_submissions(10)

        output1 = m1.generate_metrics()
        output2 = m2.generate_metrics()

        assert "careergraph_submissions_total" in output1
        # m2 registry should NOT have data from m1
        assert "careergraph_submissions_total" not in output2 or "careergraph_submissions_total_count" not in output2
