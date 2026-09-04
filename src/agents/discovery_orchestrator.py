"""Discovery Orchestrator (P5c): drives the existing scanner, narrates
decisions. Source *execution* stays in JobScanner/portal crawlers; this
agent chooses when/what to run and publishes what was found so the
Application Agent can react. No new crawler engine here."""
import importlib
import logging
import time
from typing import Any, Dict, List, Optional

from src.agents.base import BaseAgent
from src.core.events import Event, EventType

log = logging.getLogger("careergraph.agents.discovery")

_SCANNER_MOD = "src.pipeline.1_discovery.scanner"


class DiscoveryOrchestratorAgent(BaseAgent):
    def __init__(self, scanner: Optional[Any] = None,
                 name: str = "discovery_orchestrator") -> None:
        super().__init__(name)
        self.handles = [EventType.CRAWLER_FAILED]
        self._scanner = scanner
        self._started = time.monotonic()

    @property
    def scanner(self):
        if self._scanner is None:
            mod = importlib.import_module(_SCANNER_MOD)
            self._scanner = mod.JobScanner()  # all constructor kwargs optional
                                              # (scanner.py:23); pass none here
        return self._scanner

    def on_event(self, event: Event) -> None:
        if event.event_type == EventType.CRAWLER_FAILED:
            self.decide("degrade_note",
                        str(event.payload.get("error", "crawler failed")),
                        job_id=event.subject_id,
                        metadata=dict(event.payload))

    def _available_sources(self) -> List[str]:
        try:
            pc = importlib.import_module("src.pipeline.1_discovery.portal_crawler")
            crawlers = pc.CrawlerRegistry().list_available_crawlers()
        except Exception:  # noqa: BLE001
            crawlers = []
        return sorted(set(crawlers + ["jobspy", "remotive", "adzuna",
                                      "echojobs", "remoteok", "jobicy", "hn_jobs"]))

    def _resolve_companies(self, company_names: Optional[List[str]]):
        """names -> watchlist config dicts (scan_all takes dicts, not strings)."""
        if not company_names:
            return None  # scan_all falls back to scanner.load_companies()
        wanted = {n.lower() for n in company_names}
        return [c for c in self.scanner.load_companies()
                if str(c.get("name", "")).lower() in wanted]

    def run_once(self, company_names: Optional[List[str]] = None,
                 include_aggregators: bool = True,
                 filter_h1b: bool = False) -> Dict[str, Any]:
        companies = self._resolve_companies(company_names)
        sources = self._available_sources()
        self.decide("select_sources",
                    f"run scan across {len(sources)} source families",
                    metadata={"sources": sources, "companies": company_names,
                              "include_aggregators": include_aggregators})
        t0 = time.monotonic()
        jobs = self.scanner.scan_all(companies=companies,
                                     filter_h1b=filter_h1b,
                                     include_aggregators=include_aggregators)
        for job in jobs:
            self._bus.publish(self._to_event(job))
        summary = {"jobs_ingested": len(jobs), "sources": sources,
                   "duration_sec": round(time.monotonic() - t0, 2)}
        self.decide("scan_complete", f"ingested {len(jobs)} jobs",
                    metadata=summary)
        return summary

    @staticmethod
    def _to_event(job) -> Event:
        return Event(event_type=EventType.JOB_DISCOVERED,
                     source="discovery_orchestrator", subject_id=job.id,
                     payload={"title": job.title, "company": job.company,
                              "url": job.url, "original_source": job.source})
