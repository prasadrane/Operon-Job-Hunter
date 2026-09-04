"""Scout Titan: Big Tech Harvester (Amazon, Microsoft, Google)."""

import importlib
import logging
from typing import Any, Dict, List, Optional
from src.core.models import JobPosting
from .base import BaseDiscoveryAgent

_crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
PortalCrawler = getattr(_crawler_mod, "PortalCrawler")

log = logging.getLogger(__name__)


class ScoutTitanAgent(BaseDiscoveryAgent):
    """Specialized in direct harvesting of Big Tech & FAANG career APIs."""

    def __init__(self, timeout: float = 15.0) -> None:
        super().__init__(name="Big Tech Harvester", codename="Scout Titan", timeout=timeout)
        self.portal_crawler = PortalCrawler(timeout=timeout)

    def run(self, companies: Optional[List[Dict[str, Any]]] = None) -> List[JobPosting]:
        """Harvest software engineering jobs from Amazon, Microsoft, Google, etc."""
        discovered: List[JobPosting] = []
        target_portals = {"amazon", "microsoft", "google"}

        active_comps = companies or [
            {"name": "Amazon", "portal_type": "amazon", "board_token": "amazon", "enabled": True},
            {"name": "Microsoft", "portal_type": "microsoft", "board_token": "microsoft", "enabled": True},
            {"name": "Google", "portal_type": "google", "board_token": "google", "enabled": True},
        ]

        for comp in active_comps:
            if not comp.get("enabled", True):
                continue
            portal = str(comp.get("portal_type", "")).lower()
            if portal not in target_portals:
                continue

            name = comp.get("name", "Big Tech")
            board_token = comp.get("board_token") or name.lower()

            try:
                self.log_action(f"Harvesting Big Tech career endpoint for {name}...")
                jobs = self.portal_crawler.crawl(
                    portal_type=portal,
                    board_token=board_token,
                    company_name=name,
                )
                discovered.extend(jobs)
            except Exception as exc:
                log.warning("Scout Titan error on %s: %s", name, exc)

        self.total_discovered += len(discovered)
        self.log_action(f"Titan sprint complete. Harvested {len(discovered)} Big Tech roles.")
        return discovered
