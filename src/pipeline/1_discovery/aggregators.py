"""High-Volume Free Tech Job Aggregators: RemoteOK, Jobicy, and Hacker News Who is Hiring."""

import asyncio
import html
import logging
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import httpx

from src.core.models import JobPosting, JobStatus
from .date_parser import parse_job_posted_date
from .portal_crawler import classify_portal_from_url, clean_html_description

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


class RemoteOKCrawler:
    """Crawler for RemoteOK public JSON API (100% free, high-volume remote US tech roles)."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.url = "https://remoteok.com/api"

    def fetch_jobs(self, limit: int = 50) -> List[JobPosting]:
        """Fetch remote software engineering jobs from RemoteOK (synchronous)."""
        jobs: List[JobPosting] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                resp = client.get(self.url)
                if resp.status_code != 200:
                    return []
                data = resp.json()

            if not isinstance(data, list):
                return []

            for item in data:
                if not isinstance(item, dict) or "legal" in item or "position" not in item:
                    continue

                title = str(item.get("position", "Software Engineer")).strip()
                company = str(item.get("company", "Tech Company")).strip()
                apply_url = str(item.get("apply_url") or item.get("url") or "").strip()
                if not apply_url:
                    continue

                raw_desc = item.get("description", "")
                clean_desc = clean_html_description(raw_desc)
                location = item.get("location") or "Remote, United States"
                posted_at = parse_job_posted_date(item.get("date"))

                posting_id = str(item.get("id") or item.get("slug") or hash(apply_url))
                portal_type = classify_portal_from_url(apply_url)

                jobs.append(
                    JobPosting(
                        id=f"remoteok_{posting_id}",
                        company=company,
                        title=title,
                        url=apply_url,
                        portal_type=portal_type,
                        source="remoteok_api",
                        status=JobStatus.DISCOVERED,
                        location=location,
                        description=clean_desc,
                        posted_at=posted_at,
                        raw_data=item,
                    )
                )

                if len(jobs) >= limit:
                    break
        except Exception as exc:
            log.warning("RemoteOK crawler failed: %s", exc)

        return jobs

    async def async_fetch_jobs(
        self,
        limit: int = 50,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch remote software engineering jobs from RemoteOK asynchronously."""
        jobs: List[JobPosting] = []

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(self.url)
                if resp.status_code != 200:
                    return []
                data = resp.json()

                if not isinstance(data, list):
                    return []

                for item in data:
                    if not isinstance(item, dict) or "legal" in item or "position" not in item:
                        continue

                    title = str(item.get("position", "Software Engineer")).strip()
                    company = str(item.get("company", "Tech Company")).strip()
                    apply_url = str(item.get("apply_url") or item.get("url") or "").strip()
                    if not apply_url:
                        continue

                    raw_desc = item.get("description", "")
                    clean_desc = clean_html_description(raw_desc)
                    location = item.get("location") or "Remote, United States"
                    posted_at = parse_job_posted_date(item.get("date"))

                    posting_id = str(item.get("id") or item.get("slug") or hash(apply_url))
                    portal_type = classify_portal_from_url(apply_url)

                    jobs.append(
                        JobPosting(
                            id=f"remoteok_{posting_id}",
                            company=company,
                            title=title,
                            url=apply_url,
                            portal_type=portal_type,
                            source="remoteok_api",
                            status=JobStatus.DISCOVERED,
                            location=location,
                            description=clean_desc,
                            posted_at=posted_at,
                            raw_data=item,
                        )
                    )

                    if len(jobs) >= limit:
                        break
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("RemoteOK async crawler failed: %s", exc)

        return jobs


class JobicyCrawler:
    """Crawler for Jobicy Engineering API (free remote US tech jobs)."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.url = "https://jobicy.com/api/v2/remote-jobs?count=100&geo=usa&industry=engineering"

    def fetch_jobs(self, limit: int = 50) -> List[JobPosting]:
        """Fetch US software engineering jobs from Jobicy API (synchronous)."""
        jobs: List[JobPosting] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                resp = client.get(self.url)
                if resp.status_code != 200:
                    return []
                data = resp.json()

            items = data.get("jobs", []) if isinstance(data, dict) else []
            for item in items:
                title = str(item.get("jobTitle", "Software Engineer")).strip()
                company = str(item.get("companyName", "Tech Company")).strip()
                job_url = str(item.get("url", "")).strip()
                if not job_url:
                    continue

                posting_id = str(item.get("id", hash(job_url)))
                clean_desc = clean_html_description(item.get("jobDescription", ""))
                location = item.get("jobGeo") or "United States"
                posted_at = parse_job_posted_date(item.get("pubDate"))
                portal_type = classify_portal_from_url(job_url)

                jobs.append(
                    JobPosting(
                        id=f"jobicy_{posting_id}",
                        company=company,
                        title=title,
                        url=job_url,
                        portal_type=portal_type,
                        source="jobicy_api",
                        status=JobStatus.DISCOVERED,
                        location=location,
                        description=clean_desc,
                        posted_at=posted_at,
                        raw_data=item,
                    )
                )

                if len(jobs) >= limit:
                    break
        except Exception as exc:
            log.warning("Jobicy crawler failed: %s", exc)

        return jobs

    async def async_fetch_jobs(
        self,
        limit: int = 50,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch US software engineering jobs from Jobicy API asynchronously."""
        jobs: List[JobPosting] = []

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(self.url)
                if resp.status_code != 200:
                    return []
                data = resp.json()

                items = data.get("jobs", []) if isinstance(data, dict) else []
                for item in items:
                    title = str(item.get("jobTitle", "Software Engineer")).strip()
                    company = str(item.get("companyName", "Tech Company")).strip()
                    job_url = str(item.get("url", "")).strip()
                    if not job_url:
                        continue

                    posting_id = str(item.get("id", hash(job_url)))
                    clean_desc = clean_html_description(item.get("jobDescription", ""))
                    location = item.get("jobGeo") or "United States"
                    posted_at = parse_job_posted_date(item.get("pubDate"))
                    portal_type = classify_portal_from_url(job_url)

                    jobs.append(
                        JobPosting(
                            id=f"jobicy_{posting_id}",
                            company=company,
                            title=title,
                            url=job_url,
                            portal_type=portal_type,
                            source="jobicy_api",
                            status=JobStatus.DISCOVERED,
                            location=location,
                            description=clean_desc,
                            posted_at=posted_at,
                            raw_data=item,
                        )
                    )

                    if len(jobs) >= limit:
                        break
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Jobicy async crawler failed: %s", exc)

        return jobs


class HackerNewsJobsCrawler:
    """Crawler for monthly Hacker News 'Ask HN: Who is Hiring?' threads via Firebase REST API."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.firebase_base = "https://hacker-news.firebaseio.com/v0"

    def _get_latest_who_is_hiring_kids(self) -> List[int]:
        """Find the latest 'Who is Hiring' thread from user 'whoishiring' and return top comment IDs."""
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                resp = client.get(f"{self.firebase_base}/user/whoishiring.json")
                if resp.status_code != 200:
                    return []
                user_data = resp.json()
                submitted = user_data.get("submitted", [])[:10]

                for item_id in submitted:
                    item_resp = client.get(f"{self.firebase_base}/item/{item_id}.json")
                    if item_resp.status_code == 200:
                        item_data = item_resp.json()
                        title = item_data.get("title", "")
                        if "who is hiring" in title.lower():
                            return item_data.get("kids", [])[:100]
        except Exception as exc:
            log.warning("Failed querying Hacker News whoishiring user: %s", exc)

        return []

    def fetch_jobs(self, limit: int = 25) -> List[JobPosting]:
        """Fetch and parse job postings from HN 'Who is Hiring?' comments."""
        jobs: List[JobPosting] = []
        comment_ids = self._get_latest_who_is_hiring_kids()
        if not comment_ids:
            return []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                for cid in comment_ids[:limit]:
                    resp = client.get(f"{self.firebase_base}/item/{cid}.json")
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    if not data or data.get("deleted") or not data.get("text"):
                        continue

                    raw_html = data.get("text", "")
                    clean_text = clean_html_description(raw_html)
                    first_line = clean_text.split("\n")[0] if clean_text else ""

                    parts = [p.strip() for p in first_line.split("|")]
                    company = parts[0] if parts else "HN Startup"
                    title = parts[1] if len(parts) > 1 else "Software Engineer"
                    location = parts[2] if len(parts) > 2 else "Remote / United States"

                    urls = re.findall(r'href=[\'"]?(https?://[^\'" >]+)', raw_html)
                    if not urls:
                        urls = re.findall(r"https?://[^\s<>\"')]+", clean_text)
                    job_url = urls[0] if urls else f"https://news.ycombinator.com/item?id={cid}"

                    posted_at = parse_job_posted_date(data.get("time"))
                    portal_type = classify_portal_from_url(job_url)

                    jobs.append(
                        JobPosting(
                            id=f"hn_{cid}",
                            company=company,
                            title=title,
                            url=job_url,
                            portal_type=portal_type,
                            source="hackernews_whoishiring",
                            status=JobStatus.DISCOVERED,
                            location=location,
                            description=clean_text,
                            posted_at=posted_at,
                            raw_data=data,
                        )
                    )
        except Exception as exc:
            log.warning("HackerNews jobs fetch failed: %s", exc)

        return jobs

    async def async_fetch_jobs(
        self,
        limit: int = 25,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch and parse job postings from HN 'Who is Hiring?' comments asynchronously."""
        jobs: List[JobPosting] = []
        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(f"{self.firebase_base}/user/whoishiring.json")
                if resp.status_code != 200:
                    return []
                user_data = resp.json()
                submitted = user_data.get("submitted", [])[:10]
                comment_ids = []
                for item_id in submitted:
                    item_resp = await local_client.get(f"{self.firebase_base}/item/{item_id}.json")
                    if item_resp.status_code == 200:
                        item_data = item_resp.json()
                        if "who is hiring" in item_data.get("title", "").lower():
                            comment_ids = item_data.get("kids", [])[:100]
                            break
                if not comment_ids:
                    return []

                for cid in comment_ids[:limit]:
                    c_resp = await local_client.get(f"{self.firebase_base}/item/{cid}.json")
                    if c_resp.status_code != 200:
                        continue
                    data = c_resp.json()
                    if not data or data.get("deleted") or not data.get("text"):
                        continue
                    raw_html = data.get("text", "")
                    clean_text = clean_html_description(raw_html)
                    first_line = clean_text.split("\n")[0] if clean_text else ""
                    parts = [p.strip() for p in first_line.split("|")]
                    company = parts[0] if parts else "HN Startup"
                    title = parts[1] if len(parts) > 1 else "Software Engineer"
                    location = parts[2] if len(parts) > 2 else "Remote / United States"
                    urls = re.findall(r'href=[\'"]?(https?://[^\'" >]+)', raw_html)
                    if not urls:
                        urls = re.findall(r"https?://[^\s<>\"')]+", clean_text)
                    job_url = urls[0] if urls else f"https://news.ycombinator.com/item?id={cid}"
                    posted_at = parse_job_posted_date(data.get("time"))
                    portal_type = classify_portal_from_url(job_url)
                    jobs.append(JobPosting(id=f"hn_{cid}", company=company, title=title, url=job_url, portal_type=portal_type, source="hackernews_whoishiring", status=JobStatus.DISCOVERED, location=location, description=clean_text, posted_at=posted_at, raw_data=data))
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("HackerNews async jobs fetch failed: %s", exc)

        return jobs


class YCStartupCrawler:
    """Crawler for Y Combinator 'Work at a Startup' public tech roles API."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.url = "https://www.workatastartup.com/api/jobs"

    def fetch_jobs(self, limit: int = 50) -> List[JobPosting]:
        """Fetch YC startup jobs synchronously."""
        return asyncio.run(self.async_fetch_jobs(limit=limit))

    async def async_fetch_jobs(
        self,
        limit: int = 50,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch YC startup jobs asynchronously."""
        jobs: List[JobPosting] = []
        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(self.url)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("jobs", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    for item in items:
                        title = str(item.get("title", "Software Engineer")).strip()
                        company = str(item.get("company_name") or item.get("company", "YC Startup")).strip()
                        job_url = str(item.get("url") or item.get("apply_url") or "").strip()
                        if not job_url:
                            continue
                        posting_id = str(item.get("id") or hash(job_url))
                        location = item.get("location") or "Remote / United States"
                        desc = clean_html_description(item.get("description", ""))
                        posted_at = parse_job_posted_date(item.get("created_at") or item.get("posted_at"))
                        portal_type = classify_portal_from_url(job_url)

                        jobs.append(
                            JobPosting(
                                id=f"yc_{posting_id}",
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type=portal_type,
                                source="yc_workatastartup",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=desc,
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )
                        if len(jobs) >= limit:
                            break
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("YCStartupCrawler async fetch failed: %s", exc)

        return jobs


class BuiltInCrawler:
    """Crawler for BuiltIn Tech Hub feeds (SF, NYC, Austin, Seattle, Chicago)."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.hub_urls = [
            "https://builtin.com/api/jobs?category=engineering&location=usa",
        ]

    def fetch_jobs(self, limit: int = 50) -> List[JobPosting]:
        """Fetch BuiltIn jobs synchronously."""
        return asyncio.run(self.async_fetch_jobs(limit=limit))

    async def async_fetch_jobs(
        self,
        limit: int = 50,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch BuiltIn jobs asynchronously."""
        jobs: List[JobPosting] = []
        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                for url in self.hub_urls:
                    resp = await local_client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data.get("jobs", []) if isinstance(data, dict) else []
                        for item in items:
                            title = str(item.get("title", "Software Engineer")).strip()
                            company = str(item.get("company_name", "Tech Employer")).strip()
                            job_url = str(item.get("url", "")).strip()
                            if not job_url:
                                continue
                            posting_id = str(item.get("id", hash(job_url)))
                            location = item.get("location") or "United States"
                            desc = clean_html_description(item.get("body", ""))
                            posted_at = parse_job_posted_date(item.get("posted"))
                            portal_type = classify_portal_from_url(job_url)

                            jobs.append(
                                JobPosting(
                                    id=f"builtin_{posting_id}",
                                    company=company,
                                    title=title,
                                    url=job_url,
                                    portal_type=portal_type,
                                    source="builtin_api",
                                    status=JobStatus.DISCOVERED,
                                    location=location,
                                    description=desc,
                                    posted_at=posted_at,
                                    raw_data=item,
                                )
                            )
                            if len(jobs) >= limit:
                                break
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("BuiltInCrawler async fetch failed: %s", exc)

        return jobs


class WellfoundCrawler:
    """Crawler for Wellfound (AngelList Talent) startup feeds."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.url = "https://wellfound.com/api/public/jobs"

    def fetch_jobs(self, limit: int = 50) -> List[JobPosting]:
        """Fetch Wellfound jobs synchronously."""
        return asyncio.run(self.async_fetch_jobs(limit=limit))

    async def async_fetch_jobs(
        self,
        limit: int = 50,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch Wellfound jobs asynchronously."""
        jobs: List[JobPosting] = []
        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(self.url)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("jobs", []) if isinstance(data, dict) else []
                    for item in items:
                        title = str(item.get("title", "Software Engineer")).strip()
                        company = str(item.get("company_name", "Startup")).strip()
                        job_url = str(item.get("url", "")).strip()
                        if not job_url:
                            continue
                        posting_id = str(item.get("id", hash(job_url)))
                        location = item.get("location") or "United States"
                        desc = clean_html_description(item.get("description", ""))
                        posted_at = parse_job_posted_date(item.get("published_at"))
                        portal_type = classify_portal_from_url(job_url)

                        jobs.append(
                            JobPosting(
                                id=f"wellfound_{posting_id}",
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type=portal_type,
                                source="wellfound_api",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=desc,
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )
                        if len(jobs) >= limit:
                            break
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("WellfoundCrawler async fetch failed: %s", exc)

        return jobs

