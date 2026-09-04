"""JobSpy multi-board scraper module for CareerGraph AI."""

import asyncio
import concurrent.futures
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from src.core.models import JobPosting, JobStatus
from .date_parser import parse_job_posted_date

log = logging.getLogger(__name__)

try:
    from jobspy import scrape_jobs
except ImportError:
    scrape_jobs = None


US_SWE_TARGET_ROLES = [
    "Software Engineer",
    "Senior Software Engineer",
    "Backend Engineer",
    "Full Stack Engineer",
    "Platform Engineer",
    "Cloud Engineer",
    "Distributed Systems Engineer",
    ".NET Engineer",
    "Staff Software Engineer",
]


class JobSpyScraper:
    """High-yield, parallelized multi-board job discovery scraper utilizing python-jobspy."""

    def __init__(self, default_sites: Optional[List[str]] = None) -> None:
        # Pruned default sites to exclude Cloudflare-blocked boards (Glassdoor, ZipRecruiter)
        self.default_sites = default_sites or ["linkedin", "indeed"]

    def _scrape_dataframe(
        self,
        site_name: List[str],
        search_term: str,
        location: str,
        results_wanted: int,
    ) -> List[Dict[str, Any]]:
        """Internal worker executing scrape_jobs and converting DataFrame to dictionary records."""
        if scrape_jobs is None:
            log.info("python-jobspy is not installed. Skipping external board scraping.")
            return []

        try:
            jobs_df = scrape_jobs(
                site_name=site_name,
                search_term=search_term,
                location=location,
                results_wanted=results_wanted,
                country_indeed="USA",
            )
            if jobs_df is None or jobs_df.empty:
                return []
            return jobs_df.to_dict(orient="records")
        except Exception as exc:
            log.warning("JobSpy scraping failed: %s", exc)
            return []

    def search_jobs(
        self,
        search_term: str = "Software Engineer",
        location: str = "United States",
        limit: int = 25,
        sites: Optional[List[str]] = None,
    ) -> List[JobPosting]:
        """Scrape jobs across multiple boards and map to JobPosting models."""
        target_sites = sites or self.default_sites
        records = self._scrape_dataframe(
            site_name=target_sites,
            search_term=search_term,
            location=location,
            results_wanted=limit,
        )

        postings: List[JobPosting] = []
        for idx, rec in enumerate(records):
            url = rec.get("job_url") or rec.get("url") or ""
            if not url:
                continue

            company = str(rec.get("company") or "Unknown Company").strip()
            title = str(rec.get("title") or "Software Engineer").strip()
            loc_val = str(rec.get("location") or location).strip()
            site_name = str(rec.get("site") or "jobspy").lower()
            desc = str(rec.get("description") or "")
            posted_at = parse_job_posted_date(rec.get("date_posted"))

            job_id = f"jobspy_{site_name}_{idx}_{hash(url) & 0xFFFFFFFF}"

            postings.append(
                JobPosting(
                    id=job_id,
                    company=company,
                    title=title,
                    url=str(url),
                    portal_type="jobspy",
                    source=f"jobspy_{site_name}",
                    status=JobStatus.DISCOVERED,
                    location=loc_val,
                    description=desc,
                    posted_at=posted_at,
                    raw_data=rec,
                )
            )

        return postings

    def sweep_us_software_engineering_roles(
        self,
        roles: Optional[List[str]] = None,
        location: str = "United States",
        limit_per_role: int = 25,
        sites: Optional[List[str]] = None,
        max_workers: int = 4,
    ) -> List[JobPosting]:
        """Execute a concurrent nationwide sweep across key Software Engineering job titles."""
        target_roles = roles or US_SWE_TARGET_ROLES
        aggregated: List[JobPosting] = []
        seen_urls = set()

        def _worker(role: str) -> List[JobPosting]:
            try:
                log.info("JobSpy sweeping role: %s in %s...", role, location)
                return self.search_jobs(search_term=role, location=location, limit=limit_per_role, sites=sites)
            except Exception as exc:
                log.warning("Failed sweeping role %s: %s", role, exc)
                return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_worker, role) for role in target_roles]
            for fut in concurrent.futures.as_completed(futures):
                for job in fut.result():
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        aggregated.append(job)

        return aggregated

    async def async_sweep_us_software_engineering_roles(
        self,
        roles: Optional[List[str]] = None,
        location: str = "United States",
        limit_per_role: int = 25,
        sites: Optional[List[str]] = None,
    ) -> List[JobPosting]:
        """Asynchronously execute role sweeps in background threads."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self.sweep_us_software_engineering_roles,
            roles,
            location,
            limit_per_role,
            sites,
        )
