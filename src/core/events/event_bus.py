"""Synchronous in-process domain event bus (P5a foundation).

Handlers run inline on the publishing thread and must be fast and
non-blocking; anything that needs the network belongs in an agent that
*subscribes* here and dispatches to its own worker (P5c). Exceptions in
one handler are logged and never affect sibling handlers (the return
count from publish() counts invoked handlers, not successful ones).
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .event_types import EventType

logger = logging.getLogger("careergraph.events")

Handler = Callable[["Event"], None]


@dataclass
class Event:
    """One domain event. payload/subject_id must be JSON-serializable."""

    event_type: EventType
    source: str
    subject_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": EventType(self.event_type).value,
            "source": self.source,
            "subject_id": self.subject_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


class EventBus:
    """Subscribe/publish pub-sub with handler isolation. Not thread-safe by
    design — publish() is called from whichever worker thread produces the
    event; subscription changes happen at wiring time (runtime start)."""

    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[Handler]] = {}

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        handlers = self._subscribers.get(event_type, [])
        self._subscribers[event_type] = [h for h in handlers if h is not handler]

    def publish(self, event: Event) -> int:
        handlers = list(self._subscribers.get(event.event_type, []))
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 — isolation is the contract
                logger.error(
                    "Event handler %r failed for %s: %s",
                    getattr(handler, "__qualname__", handler),
                    event.event_type.value,
                    exc,
                )
        return len(handlers)


_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def reset_event_bus() -> None:
    """Drop the singleton. Test-only hook; production code never calls this."""
    global _global_bus
    _global_bus = None
