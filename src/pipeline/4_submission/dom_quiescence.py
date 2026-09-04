"""DOM Quiescence helper for robust Playwright automation waiting."""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def wait_for_dom_quiescence(
    page_or_frame: Any,
    debounce_ms: int = 500,
    max_timeout_s: float = 2.5,
) -> None:
    """Wait for DOM rendering and network events to settle before interacting with elements.
    
    Args:
        page_or_frame: Playwright Page or Frame instance.
        debounce_ms: Milliseconds to wait after DOM ready state to let dynamic mutations settle.
        max_timeout_s: Maximum total time to spend waiting.
    """
    if not page_or_frame:
        return

    start_time = time.perf_counter()

    # Attempt to wait for domcontentloaded state
    if hasattr(page_or_frame, "wait_for_load_state"):
        try:
            timeout_ms = min(int(max_timeout_s * 1000), 2000)
            page_or_frame.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            logger.debug("wait_for_load_state(domcontentloaded) timed out or not supported.")

    # Debounce delay to ensure dynamic scripts / microtasks settle
    remaining = max_timeout_s - (time.perf_counter() - start_time)
    delay = min(debounce_ms / 1000.0, max(0.05, remaining))
    time.sleep(delay)
