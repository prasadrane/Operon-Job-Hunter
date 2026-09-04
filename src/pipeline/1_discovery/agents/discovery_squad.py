"""Discovery Squad Orchestrator coordinating all 5 subagents with canonical deduplication."""

import concurrent.futures
import importlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import yaml

from src.core.models import JobPosting
from .base import canonicalize_url
from .scout_falcon import ScoutFalconAgent
from .scout_atlas import ScoutAtlasAgent
from .scout_titan import ScoutTitanAgent
from .scout_horizon import ScoutHorizonAgent
from .scout_aegis import ScoutAegisAgent

log = logging.getLogger(__name__)


class DiscoverySquadOrchestrator:
    """Coordinates parallel execution of the 5 Discovery Sub-Agents and synchronizes with the ledger."""

    def __init__(self, companies_file: Optional[str] = None, job_repo: Optional[Any] = None) -> None:
        self.companies_file = companies_file
        self.job_repo = job_repo
        self.falcon = ScoutFalconAgent()
        self.atlas = ScoutAtlasAgent()
        self.titan = ScoutTitanAgent()
        self.horizon = ScoutHorizonAgent()
        self.aegis = ScoutAegisAgent()

    def load_companies(self) -> List[Dict[str, Any]]:
        """Load company watchlist configuration."""
        target_path = self.companies_file
        if not target_path:
            from src.core.config import get_settings
            target_path = str(get_settings().companies_yaml_path)

        if not target_path or not Path(target_path).exists():
            return []

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("companies", []) if isinstance(data, dict) else []
        except Exception:
            return []

    def run_squad(
        self,
        companies: Optional[List[Dict[str, Any]]] = None,
        max_horizon_pages: int = 2,
    ) -> List[JobPosting]:
        """Execute concurrent fan-out across Falcon, Atlas, Titan, and Horizon, then filter through Aegis."""
        company_list = companies if companies is not None else self.load_companies()
        raw_pool: List[JobPosting] = []

        log.info("🛰️ Launching Autonomous 5-Agent Discovery Squad...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            fut_falcon = executor.submit(self.falcon.run, company_list)
            fut_atlas = executor.submit(self.atlas.run, company_list)
            fut_titan = executor.submit(self.titan.run, company_list)
            fut_horizon = executor.submit(self.horizon.run, max_horizon_pages)

            for fut in [fut_falcon, fut_atlas, fut_titan, fut_horizon]:
                try:
                    jobs = fut.result()
                    raw_pool.extend(jobs)
                except Exception as exc:
                    log.warning("Discovery squad worker exception: %s", exc)

        # Canonical URL deduplication
        seen_canonical_urls: Set[str] = set()
        deduped_pool: List[JobPosting] = []

        for job in raw_pool:
            c_url = canonicalize_url(job.url)
            if not c_url or c_url in seen_canonical_urls:
                continue
            seen_canonical_urls.add(c_url)
            deduped_pool.append(job)

        # Quality Gate: Scout Aegis H-1B validation and blocker purge
        final_verified_jobs, purged_blockers = self.aegis.sanitize_and_verify(deduped_pool)

        # Persistence to database repository
        if self.job_repo:
            for job in final_verified_jobs:
                existing = self.job_repo.get_job(job.id)
                if existing is None:
                    self.job_repo.insert_job(job)

        log.info("🛰️ Discovery Squad mission completed. %d unique verified roles ready for evaluation.", len(final_verified_jobs))
        return final_verified_jobs
