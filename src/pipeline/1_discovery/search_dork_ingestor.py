"""Search Engine Dork Ingestor targeting public ATS endpoints for unmonitored companies."""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from src.core.models import JobPosting, JobStatus
from .portal_crawler import classify_portal_from_url

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class SearchDorkIngestor:
    """Discovers fresh unmonitored job postings by querying public ATS domains via search dorks."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def build_dork_queries(self) -> List[str]:
        """Generate targeted ATS search queries for senior backend & cloud roles."""
        return [
            'site:boards.greenhouse.io ("C#" OR ".NET") "AWS" "United States"',
            'site:jobs.lever.co ("C#" OR ".NET") "AWS" "Remote"',
            'site:jobs.ashbyhq.com ("Backend Engineer" OR "Software Engineer") "AWS"',
        ]

    async def async_search_ats_urls(
        self,
        query: str,
        limit: int = 20,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Query search endpoint and parse matching ATS job URLs."""
        jobs: List[JobPosting] = []
        # Free search engine duckduckgo lite / html endpoint
        encoded_q = query.replace(" ", "+").replace('"', "%22")
        url = f"https://html.duckduckgo.com/html/?q={encoded_q}"
        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(url)
                if resp.status_code == 200:
                    urls = re.findall(r'href="(https?://(?:boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com)/[^"]+)"', resp.text)
                    for raw_url in urls:
                        clean_url = raw_url.split("&")[0].split("?")[0]
                        portal_type = classify_portal_from_url(clean_url)
                        parts = clean_url.strip("/").split("/")
                        company_slug = parts[-2] if len(parts) >= 2 else "Tech Company"
                        company = company_slug.replace("-", " ").replace("_", " ").title()
                        posting_id = str(hash(clean_url))

                        jobs.append(
                            JobPosting(
                                id=f"dork_{portal_type}_{posting_id}",
                                company=company,
                                title="Software Engineer",
                                url=clean_url,
                                portal_type=portal_type,
                                source="search_dork_ingestor",
                                status=JobStatus.DISCOVERED,
                                location="United States",
                                description="",
                            )
                        )
                        if len(jobs) >= limit:
                            break
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Search dork ingest failed for query '%s': %s", query, exc)

        return jobs
