"""Headless Asynchronous Job Link & Expired Posting Verifier."""

import asyncio
import logging
from typing import List, Optional
import httpx
from src.core.models import JobPosting

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


class JobLinkVerifier:
    """Verifies that discovered job URLs are still live (HTTP 200) prior to staging and tailoring."""

    def __init__(self, timeout: float = 6.0) -> None:
        self.timeout = timeout

    async def verify_link(
        self,
        url: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> bool:
        """Send asynchronous HTTP HEAD/GET request to verify if URL is still reachable."""
        if not url or not url.startswith("http"):
            return False

        local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout, follow_redirects=True)
        try:
            try:
                resp = await local_client.head(url)
                if resp.status_code in (200, 301, 302, 307, 308):
                    return True
                # Fallback to GET for servers that block HEAD
                if resp.status_code in (403, 405):
                    resp_get = await local_client.get(url)
                    return resp_get.status_code == 200
                return False
            except Exception:
                return False
        finally:
            if client is None:
                await local_client.aclose()

    async def prune_expired_jobs(
        self,
        jobs: List[JobPosting],
        concurrency: int = 16,
    ) -> List[JobPosting]:
        """Prune dead, 404, or unpublished jobs concurrently."""
        valid_jobs: List[JobPosting] = []
        sem = asyncio.Semaphore(concurrency)

        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout, follow_redirects=True) as client:
            async def _check(job: JobPosting):
                async with sem:
                    is_live = await self.verify_link(job.url, client=client)
                    if is_live:
                        valid_jobs.append(job)

            tasks = [_check(j) for j in jobs]
            await asyncio.gather(*tasks, return_exceptions=True)

        return valid_jobs
