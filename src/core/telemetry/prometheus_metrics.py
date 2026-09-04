"""Prometheus metrics collector for CareerGraph AI observability.

Exposes counters, histograms, and gauges for monitoring submissions,
API requests, captcha solves, queue depths, and active submissions.
Output is Prometheus exposition format via generate_metrics().

Thread-safe: all prometheus_client primitives are thread-safe by default.
"""

from typing import Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)


class PrometheusMetrics:
    """Centralised Prometheus metrics for CareerGraph AI."""

    def __init__(self, registry: Optional[CollectorRegistry] = None) -> None:
        self.registry = registry or CollectorRegistry()

        # --- Counters ---
        self.submissions_total = Counter(
            "careergraph_submissions_total",
            "Total number of job submissions",
            ["portal_type", "status"],
            registry=self.registry,
        )
        self.captcha_solved_total = Counter(
            "careergraph_captcha_solved_total",
            "Total captcha challenges solved",
            ["captcha_type", "method"],
            registry=self.registry,
        )
        self.api_requests_total = Counter(
            "careergraph_api_requests_total",
            "Total API requests",
            ["endpoint", "status"],
            registry=self.registry,
        )

        # --- Histograms ---
        self.submission_duration = Histogram(
            "careergraph_submission_duration_seconds",
            "Time taken for job submission",
            ["portal_type"],
            registry=self.registry,
            buckets=(1, 5, 10, 30, 60, 120, 180, 300, 600),
        )
        self.api_request_duration = Histogram(
            "careergraph_api_request_duration_seconds",
            "Time taken for API requests",
            ["endpoint"],
            registry=self.registry,
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )

        # --- Gauges ---
        self.active_submissions = Gauge(
            "careergraph_active_submissions",
            "Number of currently active submissions",
            registry=self.registry,
        )
        self.queue_depth = Gauge(
            "careergraph_queue_depth",
            "Depth of named queues",
            ["queue_name"],
            registry=self.registry,
        )

    # --- Counter helpers ---

    def inc_submissions_total(self, portal_type: str, status: str) -> None:
        """Increment submission counter by portal type and outcome status."""
        self.submissions_total.labels(portal_type=portal_type, status=status).inc()

    def inc_captcha_solved_total(self, captcha_type: str, method: str) -> None:
        """Increment captcha-solved counter by type and solving method."""
        self.captcha_solved_total.labels(captcha_type=captcha_type, method=method).inc()

    def inc_api_requests_total(self, endpoint: str, status: int) -> None:
        """Increment API request counter by endpoint and HTTP status code."""
        self.api_requests_total.labels(endpoint=endpoint, status=str(status)).inc()

    # --- Histogram helpers ---

    def observe_submission_duration(self, portal_type: str, duration_sec: float) -> None:
        """Record submission duration in seconds for a portal type."""
        self.submission_duration.labels(portal_type=portal_type).observe(duration_sec)

    def observe_api_request_duration(self, endpoint: str, duration_sec: float) -> None:
        """Record API request duration in seconds for an endpoint."""
        self.api_request_duration.labels(endpoint=endpoint).observe(duration_sec)

    # --- Gauge helpers ---

    def set_active_submissions(self, count: int) -> None:
        """Set the current number of active submissions."""
        self.active_submissions.set(count)

    def set_queue_depth(self, queue_name: str, depth: int) -> None:
        """Set the current depth of a named queue."""
        self.queue_depth.labels(queue_name=queue_name).set(depth)

    # --- Output ---

    def generate_metrics(self) -> str:
        """Generate Prometheus exposition format output."""
        return generate_latest(self.registry).decode("utf-8")

    @property
    def content_type(self) -> str:
        """Prometheus content type for HTTP responses."""
        return CONTENT_TYPE_LATEST
