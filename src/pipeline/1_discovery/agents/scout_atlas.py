"""Scout Atlas: Enterprise ATS Agent (Workday, SmartRecruiters)."""

import importlib
import logging
from typing import Any, Dict, List, Optional
from src.core.models import JobPosting
from .base import BaseDiscoveryAgent

_crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
PortalCrawler = getattr(_crawler_mod, "PortalCrawler")

log = logging.getLogger(__name__)


class ScoutAtlasAgent(BaseDiscoveryAgent):
    """Specialized in deep crawling of enterprise Workday and SmartRecruiters boards."""

    def __init__(self, timeout: float = 15.0) -> None:
        super().__init__(name="Enterprise ATS Scout", codename="Scout Atlas", timeout=timeout)
        self.portal_crawler = PortalCrawler(timeout=timeout)

    def run(self, companies: List[Dict[str, Any]]) -> List[JobPosting]:
        """Crawl all Workday and SmartRecruiters corporate boards."""
        discovered: List[JobPosting] = []
        target_portals = {"workday", "smartrecruiters"}

        for comp in companies:
            if not comp.get("enabled", True):
                continue
            portal = str(comp.get("portal_type", "")).lower()
            if portal not in target_portals:
                continue

            name = comp.get("name", "Unknown")
            board_token = comp.get("board_token") or name.lower().replace(" ", "-")

            try:
                self.log_action(f"Navigating enterprise portal for {name} ({portal})...")
                jobs = self.portal_crawler.crawl(
                    portal_type=portal,
                    board_token=board_token,
                    company_name=name,
                )
                discovered.extend(jobs)
            except Exception as exc:
                log.warning("Scout Atlas error on %s: %s", name, exc)

        self.total_discovered += len(discovered)
        self.log_action(f"Atlas sprint complete. Discovered {len(discovered)} enterprise roles.")
        return discovered
