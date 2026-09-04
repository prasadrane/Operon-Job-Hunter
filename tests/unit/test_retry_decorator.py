"""Unit tests for retry decorator with exponential backoff."""

import asyncio
import time

import pytest

from src.core.resilience.retry_decorator import retry, _compute_delay


class TestRetryDecorator:
    """Sync retry behavior."""

    def test_succeeds_on_first_attempt(self):
        call_count = 0

        @retry(max_attempts=3, delay_sec=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert flaky() == "ok"
        assert call_count == 1

    def test_retries_on_specified_exception(self):
        call_count = 0

        @retry(max_attempts=3, delay_sec=0.01, exceptions=(ValueError,))
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        assert flaky() == "ok"
        assert call_count == 3

    def test_respects_max_attempts(self):
        call_count = 0

        @retry(max_attempts=3, delay_sec=0.01, exceptions=(RuntimeError,))
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("permanent")

        with pytest.raises(RuntimeError, match="permanent"):
            always_fails()
        assert call_count == 3

    def test_does_not_retry_unmatched_exception(self):
        call_count = 0

        @retry(max_attempts=3, delay_sec=0.01, exceptions=(ValueError,))
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            raises_type_error()
        assert call_count == 1

    def test_exponential_backoff(self):
        """Verify delays grow exponentially."""
        timestamps = []

        @retry(max_attempts=4, delay_sec=0.05, backoff_factor=2.0)
        def flaky():
            timestamps.append(time.monotonic())
            if len(timestamps) < 4:
                raise RuntimeError("fail")
            return "ok"

        flaky()
        assert len(timestamps) == 4
        # delays: ~0.05, ~0.10, ~0.20 (with some tolerance)
        d1 = timestamps[1] - timestamps[0]
        d2 = timestamps[2] - timestamps[1]
        d3 = timestamps[3] - timestamps[2]
        assert 0.03 <= d1 <= 0.15
        assert 0.06 <= d2 <= 0.30
        assert 0.10 <= d3 <= 0.50
        # Each delay should be roughly 2× the previous
        assert d2 > d1 * 1.3
        assert d3 > d2 * 1.3

    def test_max_delay_cap(self):
        delays = [
            _compute_delay(a, delay_sec=1.0, backoff_factor=10.0,
                           max_delay_sec=5.0, jitter=False)
            for a in range(1, 6)
        ]
        # attempt 1: 1.0, attempt 2: 10→capped 5, attempt 3+: 5
        assert delays[0] == 1.0
        assert delays[1] == 5.0
        assert all(d == 5.0 for d in delays[2:])

    def test_on_retry_callback(self):
        events = []

        def on_retry(attempt, exc, delay):
            events.append((attempt, type(exc).__name__, delay))

        @retry(max_attempts=3, delay_sec=0.01, on_retry=on_retry)
        def flaky():
            if len(events) < 2:
                raise ValueError(f"fail-{len(events)}")
            return "ok"

        flaky()
        assert len(events) == 2
        assert events[0][0] == 1
        assert events[0][1] == "ValueError"

    def test_single_attempt_no_retry(self):
        call_count = 0

        @retry(max_attempts=1, delay_sec=0.01)
        def fails():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            fails()
        assert call_count == 1

    def test_invalid_max_attempts(self):
        with pytest.raises(ValueError):
            retry(max_attempts=0)

    def test_preserves_function_metadata(self):
        @retry(max_attempts=2)
        def my_func():
            """My docstring."""
            pass

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "My docstring."


class TestRetryAsync:
    """Async retry behavior."""

    @pytest.mark.asyncio
    async def test_async_retry_succeeds(self):
        call_count = 0

        @retry(max_attempts=3, delay_sec=0.01)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient")
            return "async-ok"

        result = await flaky()
        assert result == "async-ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_retry_exhausted(self):
        call_count = 0

        @retry(max_attempts=2, delay_sec=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("permanent")

        with pytest.raises(RuntimeError):
            await always_fails()
        assert call_count == 2
