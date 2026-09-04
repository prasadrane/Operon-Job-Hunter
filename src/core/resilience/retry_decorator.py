"""Retry decorator with exponential backoff and jitter support."""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from typing import (
    Any,
    Callable,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    delay_sec: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Union[
        Tuple[Type[BaseException], ...],
        Sequence[Type[BaseException]],
    ] = (Exception,),
    on_retry: Optional[Callable[..., None]] = None,
    jitter: bool = False,
    max_delay_sec: Optional[float] = None,
) -> Callable[[F], F]:
    """Decorator for automatic retry with exponential backoff.

    Supports both sync and async callables.

    Args:
        max_attempts: Total attempts (first try + retries). Must be >= 1.
        delay_sec: Initial delay between retries in seconds.
        backoff_factor: Multiplier applied to delay after each retry.
        exceptions: Tuple/sequence of exception types that trigger a retry.
        on_retry: Optional callback invoked after each failed attempt.
            Receives (attempt_number, exception, delay_before_next).
        jitter: If True, add random jitter (0–50% of delay) to each wait.
        max_delay_sec: Cap on delay between retries (before jitter).
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if delay_sec < 0:
        raise ValueError("delay_sec must be >= 0")

    exc_tuple = tuple(exceptions)

    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc: Optional[BaseException] = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exc_tuple as exc:
                        last_exc = exc
                        if attempt >= max_attempts:
                            raise
                        delay = _compute_delay(
                            attempt, delay_sec, backoff_factor, max_delay_sec, jitter
                        )
                        logger.warning(
                            "retry: %s attempt %d/%d failed (%s); retrying in %.2fs",
                            func.__name__,
                            attempt,
                            max_attempts,
                            exc,
                            delay,
                        )
                        if on_retry is not None:
                            try:
                                on_retry(attempt, exc, delay)
                            except Exception as cb_exc:  # pragma: no cover
                                logger.warning("on_retry callback raised: %s", cb_exc)
                        await asyncio.sleep(delay)
                # Unreachable, but satisfies type checkers
                raise last_exc  # pragma: no cover

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exc_tuple as exc:
                    last_exc = exc
                    if attempt >= max_attempts:
                        raise
                    delay = _compute_delay(
                        attempt, delay_sec, backoff_factor, max_delay_sec, jitter
                    )
                    logger.warning(
                        "retry: %s attempt %d/%d failed (%s); retrying in %.2fs",
                        func.__name__,
                        attempt,
                        max_attempts,
                        exc,
                        delay,
                    )
                    if on_retry is not None:
                        try:
                            on_retry(attempt, exc, delay)
                        except Exception as cb_exc:  # pragma: no cover
                            logger.warning("on_retry callback raised: %s", cb_exc)
                    time.sleep(delay)
            raise last_exc  # pragma: no cover

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _compute_delay(
    attempt: int,
    delay_sec: float,
    backoff_factor: float,
    max_delay_sec: Optional[float],
    jitter: bool,
) -> float:
    """Compute delay for the given 1-based attempt number."""
    delay = delay_sec * (backoff_factor ** (attempt - 1))
    if max_delay_sec is not None:
        delay = min(delay, max_delay_sec)
    if jitter and delay > 0:
        delay = delay + random.random() * 0.5 * delay
    return delay
