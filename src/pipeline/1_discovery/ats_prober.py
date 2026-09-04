"""Autonomous ATS Endpoint Prober for Unmapped H-1B Sponsoring Employers."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


class ATSProber:
    """Probes candidate company domains against standard ATS API conventions."""

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout

    def _extract_slug(self, domain: str, company_name: str) -> List[str]:
        slugs = []
        if domain:
            base = domain.lower().replace("www.", "").split(".")[0].strip()
            if base:
                slugs.append(base)
        if company_name:
            c_slug = company_name.lower().strip().replace(" ", "").replace("-", "")
            if c_slug and c_slug not in slugs:
                slugs.append(c_slug)
            c_hyphen = company_name.lower().strip().replace(" ", "-")
            if c_hyphen and c_hyphen not in slugs:
                slugs.append(c_hyphen)
        return slugs

    async def probe_domain(
        self,
        domain: str,
        company_name: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[Dict[str, Any]]:
        """Probe Greenhouse, Lever, Ashby, and SmartRecruiters endpoints for a company domain."""
        slugs = self._extract_slug(domain, company_name)
        if not slugs:
            return None

        local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout, follow_redirects=True)
        try:
            for slug in slugs:
                # 1. Probe Greenhouse API
                gh_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
                try:
                    resp = await local_client.get(gh_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict) and "jobs" in data and len(data["jobs"]) > 0:
                            return {
                                "name": company_name,
                                "domain": domain,
                                "portal_type": "greenhouse",
                                "board_token": slug,
                                "careers_url": f"https://boards.greenhouse.io/{slug}",
                                "enabled": True,
                            }
                except Exception:
                    pass

                # 2. Probe Lever API
                lever_url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
                try:
                    resp = await local_client.get(lever_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list) and len(data) > 0:
                            return {
                                "name": company_name,
                                "domain": domain,
                                "portal_type": "lever",
                                "board_token": slug,
                                "careers_url": f"https://jobs.lever.co/{slug}",
                                "enabled": True,
                            }
                except Exception:
                    pass

                # 3. Probe Ashby API
                ashby_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
                try:
                    resp = await local_client.get(ashby_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict) and "jobs" in data and len(data["jobs"]) > 0:
                            return {
                                "name": company_name,
                                "domain": domain,
                                "portal_type": "ashby",
                                "board_token": slug,
                                "careers_url": f"https://jobs.ashbyhq.com/{slug}",
                                "enabled": True,
                            }
                except Exception:
                    pass

                # 4. Probe SmartRecruiters API
                sr_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
                try:
                    resp = await local_client.get(sr_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict) and "content" in data and len(data["content"]) > 0:
                            return {
                                "name": company_name,
                                "domain": domain,
                                "portal_type": "smartrecruiters",
                                "board_token": slug,
                                "careers_url": f"https://jobs.smartrecruiters.com/{slug}",
                                "enabled": True,
                            }
                except Exception:
                    pass

            return None
        finally:
            if client is None:
                await local_client.aclose()
