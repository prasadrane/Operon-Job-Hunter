"""Scout Aegis: H-1B Verification & Security Clearance Gatekeeper."""

import importlib
import logging
from typing import Any, Dict, List, Optional, Tuple
from src.core.models import JobPosting
from .base import BaseDiscoveryAgent

_h1b_mod = importlib.import_module("src.pipeline.1_discovery.h1b_checker")
H1BChecker = getattr(_h1b_mod, "H1BChecker")

log = logging.getLogger(__name__)


class ScoutAegisAgent(BaseDiscoveryAgent):
    """Specialized in quality gating, USCIS H-1B sponsorship stamping, and ITAR/clearance blocker purging."""

    def __init__(self) -> None:
        super().__init__(name="Visa & Blocker Gatekeeper", codename="Scout Aegis")
        self.h1b_checker = H1BChecker()

    def sanitize_and_verify(self, jobs: List[JobPosting]) -> Tuple[List[JobPosting], int]:
        """Verify H-1B filing history and purge explicit non-sponsorship/clearance blocker roles."""
        verified_jobs: List[JobPosting] = []
        purged_count = 0

        for job in jobs:
            eval_res = self.h1b_checker.evaluate(
                company=job.company,
                jd_text=job.description or "",
            )
            is_eligible = eval_res.get("is_eligible", False)
            jd_signal = eval_res.get("jd_sponsorship")

            if jd_signal == "no_sponsorship":
                purged_count += 1
                log.debug("Scout Aegis blocked %s at %s: explicit blocker in JD", job.title, job.company)
                continue

            job.h1b_sponsored = is_eligible
            verified_jobs.append(job)

        self.log_action(f"Aegis audit complete. Verified: {len(verified_jobs)} | Purged Blockers: {purged_count}")
        return verified_jobs, purged_count
