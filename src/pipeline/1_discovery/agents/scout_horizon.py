"""Scout Horizon: Market Sweeper (EchoJobs, RemoteOK, Jobicy, and Hacker News)."""

import importlib
import logging
from typing import Any, Dict, List, Optional
from src.core.models import JobPosting
from .base import BaseDiscoveryAgent

_crawler_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
EchoJobsFeeder = getattr(_crawler_mod, "EchoJobsFeeder")

_agg_mod = importlib.import_module("src.pipeline.1_discovery.aggregators")
RemoteOKCrawler = getattr(_agg_mod, "RemoteOKCrawler")
JobicyCrawler = getattr(_agg_mod, "JobicyCrawler")
HackerNewsJobsCrawler = getattr(_agg_mod, "HackerNewsJobsCrawler")

log = logging.getLogger(__name__)


class ScoutHorizonAgent(BaseDiscoveryAgent):
    """Specialized in broad market sweeping across high-volume zero-auth feeds and job aggregators."""

    def __init__(self, timeout: float = 20.0) -> None:
        super().__init__(name="Market Sweeper", codename="Scout Horizon", timeout=timeout)
        self.echojobs = EchoJobsFeeder(timeout=timeout)
        self.remoteok = RemoteOKCrawler(timeout=timeout)
        self.jobicy = JobicyCrawler(timeout=timeout)
        self.hackernews = HackerNewsJobsCrawler(timeout=timeout)
        self.feeder = self.echojobs

    def run(self, max_pages: int = 2, include_aggregators: bool = True) -> List[JobPosting]:
        """Fetch wide-angle aggregated software engineering postings from multi-source streams."""
        discovered: List[JobPosting] = []
        seen_urls = set()

        # 1. Stream EchoJobs ATS feed
        try:
            self.log_action(f"Streaming high-volume EchoJobs ATS feed across {max_pages} pages...")
            echo_jobs = self.echojobs.fetch_jobs(max_pages=max_pages)
            for j in echo_jobs:
                if j.url not in seen_urls:
                    seen_urls.add(j.url)
                    discovered.append(j)
        except Exception as exc:
            log.warning("Scout Horizon EchoJobs stream error: %s", exc)

        if include_aggregators:
            # 2. Stream RemoteOK US Software Developer Feed
            try:
                self.log_action("Streaming RemoteOK US Software Developer API...")
                rok_jobs = self.remoteok.fetch_jobs(limit=50)
                for j in rok_jobs:
                    if j.url not in seen_urls:
                        seen_urls.add(j.url)
                        discovered.append(j)
            except Exception as exc:
                log.warning("Scout Horizon RemoteOK stream error: %s", exc)

            # 3. Stream Jobicy Engineering Feed
            try:
                self.log_action("Streaming Jobicy USA Engineering API...")
                jobicy_jobs = self.jobicy.fetch_jobs(limit=50)
                for j in jobicy_jobs:
                    if j.url not in seen_urls:
                        seen_urls.add(j.url)
                        discovered.append(j)
            except Exception as exc:
                log.warning("Scout Horizon Jobicy stream error: %s", exc)

            # 4. Stream Hacker News "Who is Hiring?" Tech Postings
            try:
                self.log_action("Harvesting Hacker News Who is Hiring thread...")
                hn_jobs = self.hackernews.fetch_jobs(limit=30)
                for j in hn_jobs:
                    if j.url not in seen_urls:
                        seen_urls.add(j.url)
                        discovered.append(j)
            except Exception as exc:
                log.warning("Scout Horizon HackerNews stream error: %s", exc)

        self.total_discovered += len(discovered)
        self.log_action(f"Horizon sweep complete. Streamed {len(discovered)} live market postings.")
        return discovered
