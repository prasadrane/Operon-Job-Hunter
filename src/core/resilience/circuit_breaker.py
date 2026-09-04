"""Circuit breaker with three-state machine: CLOSED → OPEN → HALF_OPEN."""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, Sequence, Tuple, Type, Union

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a call is attempted while the circuit is OPEN."""

    def __init__(self, name: str, recovery_remaining: float):
        self.name = name
        self.recovery_remaining = recovery_remaining
        super().__init__(
            f"CircuitBreaker '{name}' is OPEN; "
            f"retry after {recovery_remaining:.1f}s"
        )


class CircuitBreaker:
    """Three-state circuit breaker for protecting external service calls.

    State machine:
      CLOSED  – normal operation; failures increment counter.
      OPEN    – calls rejected immediately; after recovery_timeout → HALF_OPEN.
      HALF_OPEN – one probe call allowed; success → CLOSED, failure → OPEN.

    Thread-safe via internal lock.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout_sec: int = 60,
        expected_exceptions: Union[
            Tuple[Type[BaseException], ...],
            Sequence[Type[BaseException]],
        ] = (Exception,),
        on_state_change: Union[
            Callable[[CircuitState, CircuitState], None], None
        ] = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout_sec < 0:
            raise ValueError("recovery_timeout_sec must be >= 0")

        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.expected_exceptions = tuple(expected_exceptions)
        self._on_state_change = on_state_change

        self._lock = threading.Lock()
        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        # cumulative metrics (observable for monitoring)
        self.total_calls: int = 0
        self.total_successes: int = 0
        self.total_failures: int = 0
        self.total_rejected: int = 0

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        """Return current state as a string ("closed", "open", "half_open")."""
        with self._lock:
            return self._effective_state().value

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    @property
    def metrics(self) -> dict:
        with self._lock:
            return {
                "state": self._effective_state().value,
                "failure_count": self._failure_count,
                "total_calls": self.total_calls,
                "total_successes": self.total_successes,
                "total_failures": self.total_failures,
                "total_rejected": self.total_rejected,
            }

    # ── Core API ────────────────────────────────────────────────────────────

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute func through the circuit breaker.

        Raises CircuitBreakerOpenError if circuit is OPEN and recovery timeout
        has not elapsed.
        """
        with self._lock:
            effective = self._effective_state()
            if effective is CircuitState.OPEN:
                remaining = self._time_until_half_open()
                self.total_rejected += 1
                raise CircuitBreakerOpenError(self.name, remaining)
            probe = effective is CircuitState.HALF_OPEN
            self.total_calls += 1

        try:
            result = func(*args, **kwargs)
        except self.expected_exceptions as exc:
            self._record_failure()
            logger.warning(
                "circuit_breaker[%s]: call failed (%s); failures=%d",
                self.name,
                exc,
                self._failure_count,
            )
            raise
        except BaseException:
            # Non-expected exceptions do not count toward the threshold.
            raise
        else:
            self._record_success()
            return result

    def allow_request(self) -> bool:
        """Return True if the circuit currently permits a call."""
        with self._lock:
            return self._effective_state() is not CircuitState.OPEN

    def reset(self) -> None:
        """Force the breaker back to CLOSED and zero counters."""
        with self._lock:
            self._transition(CircuitState.CLOSED)
            self._failure_count = 0
            self._last_failure_time = 0.0

    # ── Internals ───────────────────────────────────────────────────────────

    def _effective_state(self) -> CircuitState:
        """Compute effective state; must be called under lock."""
        if self._state is CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout_sec:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    def _time_until_half_open(self) -> float:
        """Seconds remaining until OPEN → HALF_OPEN transition (under lock)."""
        elapsed = time.monotonic() - self._last_failure_time
        remaining = self.recovery_timeout_sec - elapsed
        return max(0.0, remaining)

    def _record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self.total_failures += 1
            self._last_failure_time = time.monotonic()
            if self._state is CircuitState.HALF_OPEN:
                # Probe failed → reopen
                self._transition(CircuitState.OPEN)
            elif (
                self._state is CircuitState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                self._transition(CircuitState.OPEN)

    def _record_success(self) -> None:
        with self._lock:
            self.total_successes += 1
            if self._state is CircuitState.HALF_OPEN:
                # Probe succeeded → close the circuit
                self._failure_count = 0
                self._transition(CircuitState.CLOSED)
            elif self._state is CircuitState.CLOSED:
                # Optional: reset failure count on success (comment out to keep
                # a rolling count within a window). Here we reset for clarity.
                self._failure_count = 0

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state; must be called under lock."""
        if self._state is new_state:
            return
        old_state = self._state
        self._state = new_state
        logger.info(
            "circuit_breaker[%s]: %s → %s",
            self.name,
            old_state.value,
            new_state.value,
        )
        if self._on_state_change is not None:
            try:
                self._on_state_change(old_state, new_state)
            except Exception as cb_exc:  # pragma: no cover
                logger.warning("on_state_change callback raised: %s", cb_exc)
