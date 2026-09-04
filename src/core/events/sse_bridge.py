"""Bridge core domain events into the Mission Control SSE stream.

Keeps layering honest: src.core never imports src/interface at module
level. The import is resolved lazily inside the bridge (at install time,
per install — never at module top) and failures degrade to a debug log,
so daemons/CLI run fine with no UI attached. The broadcaster call adapts
to the installed interface layer: the priority-tiered
``broadcast_subagent_event(event_type, payload, priority=...)`` signature
when ``TelemetryPriority`` exists, otherwise the plain
``broadcast_subagent_event(event_type, payload)`` form.
"""
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .event_bus import Event, EventBus, get_event_bus
from .event_types import EventType

logger = logging.getLogger("careergraph.events")


def _resolve_broadcaster() -> Tuple[Optional[Callable[..., None]], Dict[str, Any]]:
    """Lazily import the interface-layer broadcaster.

    Returns (callable, extra_kwargs) or (None, {}) when the interface
    layer is unavailable (CLI/daemon without UI). Never raises.
    """
    try:
        from src.interface.api.subagent_state import (  # lazy: core -> interface
            TelemetryPriority,
            broadcast_subagent_event,
        )
        return broadcast_subagent_event, {"priority": TelemetryPriority.DECISION}
    except ImportError:
        pass
    try:
        from src.interface.api.subagent_state import broadcast_subagent_event
        return broadcast_subagent_event, {}
    except ImportError:
        return None, {}


def install_sse_bridge(
    bus: Optional[EventBus] = None,
    event_types: Optional[List[EventType]] = None,
) -> Callable[[Event], None]:
    """Subscribe the SSE forwarder. Returns the handler for later unsubscribe."""
    target = bus or get_event_bus()
    types = event_types if event_types is not None else list(EventType)

    broadcaster, call_kwargs = _resolve_broadcaster()

    def _forward(event: Event) -> None:
        nonlocal broadcaster, call_kwargs
        if broadcaster is None:
            # late re-resolve: the interface layer may have been absent at
            # install time and available now
            broadcaster, call_kwargs = _resolve_broadcaster()
        if broadcaster is None:
            logger.debug("SSE bridge: interface layer unavailable, dropping %s",
                         event.event_type.value)
            return
        broadcaster(
            f"domain_event:{event.event_type.value}",
            event.to_dict(),
            **call_kwargs,
        )

    for et in types:
        target.subscribe(et, _forward)
    return _forward
