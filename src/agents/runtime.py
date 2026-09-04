"""Agent lifecycle coordinator (P5c)."""
import logging
from typing import Dict, List, Optional

from src.agents.base import BaseAgent
from src.core.events import install_sse_bridge

log = logging.getLogger("careergraph.agents.runtime")


class AgentRuntime:
    def __init__(self, agents: List[BaseAgent], bridge_sse: bool = True) -> None:
        self.agents = list(agents)
        self.bridge_sse = bridge_sse
        self.is_running = False
        self._bridge = None

    def start(self) -> "AgentRuntime":
        if self.is_running:
            return self
        if self.bridge_sse:
            from src.core.events import get_event_bus
            self._bridge = install_sse_bridge(get_event_bus())
        for agent in self.agents:
            agent.start()
        self.is_running = True
        log.info("runtime started: %s", ", ".join(a.name for a in self.agents))
        return self

    def stop(self) -> None:
        for agent in reversed(self.agents):
            agent.stop()
        if self._bridge is not None:
            try:
                from src.core.events import get_event_bus
                for et in list(self._bridge_subscriptions()):
                    get_event_bus().unsubscribe(et, self._bridge)
            except Exception:  # noqa: BLE001
                log.debug("bridge unsubscribe incomplete", exc_info=True)
            self._bridge = None
        self.is_running = False

    def _bridge_subscriptions(self):
        from src.core.events import EventType
        return list(EventType)

    def status(self) -> Dict[str, str]:
        return {agent.name: agent.status for agent in self.agents}
