"""Scout Falcon: Fast-Path ATS Agent (Greenhouse, Lever, Ashby)."""

import importlib
import logging
from typing import Any, Dict, List, Optional
from src.core.models import JobPosting
from .base import BaseDiscoveryAgent

_crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
PortalCrawler = getattr(_crawler_mod, "PortalCrawler")

log = logging.getLogger(__name__)


class ScoutFalconAgent(BaseDiscoveryAgent):
    """Specialized in high-speed ingestion of Greenhouse, Lever, and Ashby startup/unicorn boards."""

    def __init__(self, timeout: float = 15.0) -> None:
        super().__init__(name="Fast-Path ATS Scout", codename="Scout Falcon", timeout=timeout)
        self.portal_crawler = PortalCrawler(timeout=timeout)

    def run(self, companies: List[Dict[str, Any]]) -> List[JobPosting]:
        """Crawl all enabled Greenhouse, Lever, and Ashby boards."""
        discovered: List[JobPosting] = []
        target_portals = {"greenhouse", "lever", "ashby"}

        for comp in companies:
            if not comp.get("enabled", True):
                continue
            portal = str(comp.get("portal_type", "")).lower()
            if portal not in target_portals:
                continue

            name = comp.get("name", "Unknown")
            board_token = comp.get("board_token") or name.lower().replace(" ", "-")

            try:
                self.log_action(f"Scanning {name} ({portal})...")
                jobs = self.portal_crawler.crawl(
                    portal_type=portal,
                    board_token=board_token,
                    company_name=name,
                )
                discovered.extend(jobs)
            except Exception as exc:
                log.warning("Scout Falcon error on %s: %s", name, exc)

        self.total_discovered += len(discovered)
        self.log_action(f"Falcon sprint complete. Discovered {len(discovered)} fast-path roles.")
        return discovered
