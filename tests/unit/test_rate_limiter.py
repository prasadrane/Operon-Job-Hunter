"""Unit tests for RateLimiter."""

import time
import pytest
from src.core.security.rate_limiter import RateLimiter


class TestRateLimiterBasic:
    """Basic rate limiting behaviour."""

    def test_allows_requests_under_limit(self):
        limiter = RateLimiter(requests_per_minute=5, ttl_seconds=60)
        for _ in range(5):
            assert limiter.is_allowed("1.2.3.4") is True

    def test_blocks_requests_over_limit(self):
        limiter = RateLimiter(requests_per_minute=3, ttl_seconds=60)
        assert limiter.is_allowed("1.2.3.4") is True
        assert limiter.is_allowed("1.2.3.4") is True
        assert limiter.is_allowed("1.2.3.4") is True
        # 4th request should be blocked.
        assert limiter.is_allowed("1.2.3.4") is False

    def test_different_clients_tracked_independently(self):
        limiter = RateLimiter(requests_per_minute=2, ttl_seconds=60)
        assert limiter.is_allowed("1.1.1.1") is True
        assert limiter.is_allowed("2.2.2.2") is True
        assert limiter.is_allowed("1.1.1.1") is True
        # Client 1 exhausted, client 2 still has 1 left.
        assert limiter.is_allowed("1.1.1.1") is False
        assert limiter.is_allowed("2.2.2.2") is True

    def test_disabled_limiter_always_allows(self):
        limiter = RateLimiter(requests_per_minute=1, ttl_seconds=60, enabled=False)
        for _ in range(100):
            assert limiter.is_allowed("any") is True


class TestRateLimiterTTL:
    """Sliding window expiration."""

    def test_resets_after_ttl(self):
        limiter = RateLimiter(requests_per_minute=2, ttl_seconds=1)
        assert limiter.is_allowed("client") is True
        assert limiter.is_allowed("client") is True
        assert limiter.is_allowed("client") is False

        # Wait for the window to expire.
        time.sleep(1.1)
        assert limiter.is_allowed("client") is True


class TestRateLimiterHelpers:
    """get_remaining / reset / reset_all."""

    def test_get_remaining_decrements(self):
        limiter = RateLimiter(requests_per_minute=5, ttl_seconds=60)
        assert limiter.get_remaining("x") == 5
        limiter.is_allowed("x")
        assert limiter.get_remaining("x") == 4
        limiter.is_allowed("x")
        assert limiter.get_remaining("x") == 3

    def test_reset_clears_single_client(self):
        limiter = RateLimiter(requests_per_minute=2, ttl_seconds=60)
        limiter.is_allowed("a")
        limiter.is_allowed("a")
        assert limiter.is_allowed("a") is False
        limiter.reset("a")
        assert limiter.is_allowed("a") is True

    def test_reset_all_clears_everyone(self):
        limiter = RateLimiter(requests_per_minute=1, ttl_seconds=60)
        limiter.is_allowed("a")
        limiter.is_allowed("b")
        assert limiter.is_allowed("a") is False
        assert limiter.is_allowed("b") is False
        limiter.reset_all()
        assert limiter.is_allowed("a") is True
        assert limiter.is_allowed("b") is True

    def test_get_remaining_disabled_returns_limit(self):
        limiter = RateLimiter(requests_per_minute=10, ttl_seconds=60, enabled=False)
        assert limiter.get_remaining("x") == 10

    def test_normalise_handles_whitespace_and_case(self):
        limiter = RateLimiter(requests_per_minute=2, ttl_seconds=60)
        assert limiter.is_allowed("  Client_A ") is True
        # Same bucket after normalisation.
        assert limiter.get_remaining("client_a") == 1

    def test_unknown_client_defaults_to_unknown(self):
        limiter = RateLimiter(requests_per_minute=5, ttl_seconds=60)
        assert limiter.is_allowed("") is True
        assert limiter.get_remaining("") == 4
