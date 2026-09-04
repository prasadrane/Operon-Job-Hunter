"""Reactive agent skeleton (P5c): subscribe -> delegate -> decide -> log.

Handlers must stay fast: the P5a bus is synchronous (in-publish-thread).
Subclass sets `handles`, implements on_event; heavy work is dispatched to
existing engines (pipeline, scanner) or P5b gated integrations.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.core.events import Event, EventType, get_event_bus
from src.core.telemetry.agent_ledger import AgentDecision, log_agent_decision

log = logging.getLogger("careergraph.agents")


class BaseAgent(ABC):
    def __init__(self, name: str) -> None:
        self.name = name
        self.handles: List[EventType] = []
        self.running = False
        self.status = "idle"
        self._bus = get_event_bus()
        # Cache the bound method: the bus unsubscribes by identity, and
        # `self._dispatch` creates a new bound-method object on each access.
        self._handler = self._dispatch

    @abstractmethod
    def on_event(self, event: Event) -> None:
        """React to one domain event. Must not block; must not raise."""

    def start(self) -> None:
        if self.running:
            return
        for et in self.handles:
            self._bus.subscribe(et, self._handler)
        self.running = True
        self.status = "running"
        self._mission_hook("set_agent_active")
        log.info("agent %s started (%d subscriptions)", self.name, len(self.handles))

    def stop(self) -> None:
        if not self.running:
            return
        for et in self.handles:
            self._bus.unsubscribe(et, self._handler)
        self.running = False
        self.status = "stopped"
        self._mission_hook("set_agent_sleeping")

    def _dispatch(self, event: Event) -> None:
        try:
            self.on_event(event)
        except Exception as exc:  # noqa: BLE001 — agents never crash the bus
            log.exception("agent %s crashed handling %s", self.name,
                          event.event_type.value)
            self.decide("handler_error", str(exc), job_id=event.subject_id,
                        metadata={"event_type": event.event_type.value})

    def decide(self, decision_type: str, reasoning: str,
               job_id: Optional[str] = None,
               metadata: Optional[Dict[str, Any]] = None) -> AgentDecision:
        decision = AgentDecision(agent_name=self.name, decision_type=decision_type,
                                 reasoning=reasoning, job_id=job_id,
                                 metadata=metadata or {})
        log_agent_decision(decision)
        self._bus.publish(Event(event_type=EventType.AGENT_DECISION_MADE,
                                source=self.name, subject_id=job_id,
                                payload=decision.to_record()))
        return decision

    def _mission_hook(self, fn_name: str) -> None:
        """Best-effort Mission Control status update (interface layer, lazy)."""
        try:
            from src.interface.api.subagent_state import log_agent_event
            log_agent_event(f"{self.name}: {self.status}")
        except Exception:  # noqa: BLE001 — no UI running is a normal state
            pass
