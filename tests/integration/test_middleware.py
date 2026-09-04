"""Integration tests for security middleware (CORS + rate limiting)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.security.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Helpers — build a minimal FastAPI app with the same middleware stack.
# ---------------------------------------------------------------------------


def _build_app(rate_limiter: RateLimiter) -> FastAPI:
    """Construct a minimal app mirroring routes.py middleware setup."""
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    application = FastAPI()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def rate_limit_middleware(request, call_next):
        if not rate_limiter.enabled:
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded."},
                headers={
                    "X-RateLimit-Limit": str(rate_limiter.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(rate_limiter.get_remaining(client_ip))
        return response

    @application.get("/health")
    def health():
        return {"status": "ok"}

    return application


# ---------------------------------------------------------------------------
# CORS tests
# ---------------------------------------------------------------------------


class TestCORSMiddleware:
    def test_cors_adds_allow_origin_header(self):
        limiter = RateLimiter(requests_per_minute=60, enabled=False)
        app = _build_app(limiter)
        client = TestClient(app)
        resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_blocks_unauthorised_origin(self):
        limiter = RateLimiter(requests_per_minute=60, enabled=False)
        app = _build_app(limiter)
        client = TestClient(app)
        resp = client.get("/health", headers={"Origin": "https://evil.example.com"})
        # CORS middleware does not set allow-origin for unlisted origins.
        assert resp.headers.get("access-control-allow-origin") is None

    def test_cors_preflight(self):
        limiter = RateLimiter(requests_per_minute=60, enabled=False)
        app = _build_app(limiter)
        client = TestClient(app)
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert "GET" in resp.headers.get("access-control-allow-methods", "")


# ---------------------------------------------------------------------------
# Rate limiting middleware tests
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    def test_allows_under_limit(self):
        limiter = RateLimiter(requests_per_minute=5, enabled=True)
        app = _build_app(limiter)
        client = TestClient(app)
        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_returns_429_when_exceeded(self):
        limiter = RateLimiter(requests_per_minute=2, enabled=True)
        app = _build_app(limiter)
        client = TestClient(app)
        client.get("/health")
        client.get("/health")
        resp = client.get("/health")
        assert resp.status_code == 429
        assert "Rate limit" in resp.json()["detail"]

    def test_429_response_includes_rate_headers(self):
        limiter = RateLimiter(requests_per_minute=1, enabled=True)
        app = _build_app(limiter)
        client = TestClient(app)
        client.get("/health")
        resp = client.get("/health")
        assert resp.status_code == 429
        assert resp.headers["X-RateLimit-Limit"] == "1"
        assert resp.headers["X-RateLimit-Remaining"] == "0"

    def test_success_response_includes_remaining_header(self):
        limiter = RateLimiter(requests_per_minute=10, enabled=True)
        app = _build_app(limiter)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "X-RateLimit-Remaining" in resp.headers
        assert resp.headers["X-RateLimit-Remaining"] == "9"

    def test_disabled_limiter_skips_check(self):
        limiter = RateLimiter(requests_per_minute=1, enabled=False)
        app = _build_app(limiter)
        client = TestClient(app)
        for _ in range(20):
            assert client.get("/health").status_code == 200

    def test_rate_limit_headers_on_429(self):
        limiter = RateLimiter(requests_per_minute=1, enabled=True)
        app = _build_app(limiter)
        client = TestClient(app)
        client.get("/health")
        resp = client.get("/health")
        assert resp.headers["X-RateLimit-Limit"] == "1"
        assert resp.headers["X-RateLimit-Remaining"] == "0"
