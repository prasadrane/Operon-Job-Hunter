"""In-memory sliding window rate limiter.

Thread-safe, per-client request counter with configurable TTL.
Production: swap backend for Redis (shared across workers).
"""

import time
import threading
from typing import Dict, List, Optional


class RateLimiter:
    """Sliding-window rate limiter backed by an in-memory dict.

    Each client IP has a list of request timestamps. On every call the
    window is pruned of entries older than `ttl_seconds`, then the count
    is compared against `requests_per_minute`.

    Parameters
    ----------
    requests_per_minute:
        Maximum allowed requests within the TTL window.
    ttl_seconds:
        Length of the sliding window in seconds (default 60).
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        ttl_seconds: int = 60,
        enabled: bool = True,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self._requests: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, client_ip: str) -> bool:
        """Return True and record the request if the client is under limit.

        Returns False (without recording) when the limit has been reached.
        If the limiter is disabled, always returns True.
        """
        if not self.enabled:
            return True

        now = time.monotonic()
        key = self._normalise(client_ip)

        with self._lock:
            timestamps = self._requests.get(key, [])
            cutoff = now - self.ttl_seconds
            timestamps = [ts for ts in timestamps if ts > cutoff]

            if len(timestamps) >= self.requests_per_minute:
                self._requests[key] = timestamps
                return False

            timestamps.append(now)
            self._requests[key] = timestamps
            return True

    def get_remaining(self, client_ip: str) -> int:
        """Return how many requests the client can still make in this window."""
        if not self.enabled:
            return self.requests_per_minute

        now = time.monotonic()
        key = self._normalise(client_ip)

        with self._lock:
            timestamps = self._requests.get(key, [])
            cutoff = now - self.ttl_seconds
            timestamps = [ts for ts in timestamps if ts > cutoff]
            self._requests[key] = timestamps
            remaining = self.requests_per_minute - len(timestamps)
            return max(remaining, 0)

    def reset(self, client_ip: str) -> None:
        """Clear the request history for a single client."""
        key = self._normalise(client_ip)
        with self._lock:
            self._requests.pop(key, None)

    def reset_all(self) -> None:
        """Clear all tracked clients (useful in tests)."""
        with self._lock:
            self._requests.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(client_ip: str) -> str:
        """Lower-case and strip whitespace for consistent bucket keys."""
        return (client_ip or "unknown").strip().lower()
