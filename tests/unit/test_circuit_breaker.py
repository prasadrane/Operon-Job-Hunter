"""Unit tests for CircuitBreaker state machine."""

import time

import pytest

from src.core.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)


class TestCircuitBreaker:
    """Core state machine transitions."""

    def test_starts_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == "closed"

    def test_opens_after_failure_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout_sec=60)

        def failing():
            raise RuntimeError("fail")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(failing)

        assert cb.state == "open"

    def test_open_circuit_rejects_calls(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout_sec=60)

        def failing():
            raise RuntimeError("fail")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(failing)

        assert cb.state == "open"
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should-not-run")

    def test_transitions_to_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout_sec=0.1)

        def failing():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            cb.call(failing)
        assert cb.state == "open"

        time.sleep(0.15)
        assert cb.state == "half_open"

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout_sec=0.05)

        def failing():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            cb.call(failing)
        assert cb.state == "open"

        time.sleep(0.1)
        # Successful probe → CLOSED
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state == "closed"

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout_sec=0.05)

        def failing():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            cb.call(failing)

        time.sleep(0.1)
        with pytest.raises(RuntimeError):
            cb.call(failing)
        assert cb.state == "open"

    def test_successful_call_resets_failure_count(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout_sec=60)

        def failing():
            raise RuntimeError("fail")

        # 2 failures (below threshold)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(failing)
        assert cb.failure_count == 2

        # Success resets
        cb.call(lambda: "ok")
        assert cb.failure_count == 0
        assert cb.state == "closed"

    def test_expected_exceptions_only(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            expected_exceptions=(ValueError,),
        )

        # TypeError is NOT in expected_exceptions → doesn't count
        with pytest.raises(TypeError):
            cb.call(lambda: (_ for _ in ()).throw(TypeError("x")))

        # ValueError IS expected → counts
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
        assert cb.failure_count == 1

    def test_metrics_are_observable(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout_sec=60)

        def failing():
            raise RuntimeError("fail")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(failing)

        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "x")

        metrics = cb.metrics
        assert metrics["state"] == "open"
        assert metrics["total_failures"] == 2
        assert metrics["total_rejected"] == 1
        assert metrics["total_calls"] == 2  # rejected calls don't count as calls

    def test_reset_forces_closed(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout_sec=60)

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        assert cb.state == "open"

        cb.reset()
        assert cb.state == "closed"
        assert cb.failure_count == 0

    def test_allow_request(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout_sec=60)
        assert cb.allow_request() is True

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        assert cb.allow_request() is False

    def test_on_state_change_callback(self):
        transitions = []

        def on_change(old, new):
            transitions.append((old.value, new.value))

        cb = CircuitBreaker(
            name="test", failure_threshold=1,
            recovery_timeout_sec=0.05, on_state_change=on_change,
        )

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        time.sleep(0.1)
        cb.call(lambda: "ok")

        assert ("closed", "open") in transitions
        assert ("open", "half_open") in transitions
        assert ("half_open", "closed") in transitions

    def test_invalid_failure_threshold(self):
        with pytest.raises(ValueError):
            CircuitBreaker(name="test", failure_threshold=0)

    def test_passes_args_and_kwargs(self):
        cb = CircuitBreaker(name="test")
        result = cb.call(lambda a, b=10: a + b, 5, b=20)
        assert result == 25

    def test_circuit_breaker_open_error_has_details(self):
        cb = CircuitBreaker(name="my_service", failure_threshold=1,
                            recovery_timeout_sec=100)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            cb.call(lambda: "x")

        assert exc_info.value.name == "my_service"
        assert exc_info.value.recovery_remaining > 0
        assert "my_service" in str(exc_info.value)
