import asyncio
import html
import logging
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Type
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import httpx

from src.core.models import JobPosting, JobStatus
from .date_parser import parse_job_posted_date

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def clean_html_description(raw_content: Optional[str]) -> str:
    """Clean and unescape HTML entities into human-readable plain text with preserved linebreaks."""
    if not raw_content:
        return ""
    unescaped = html.unescape(raw_content)
    if "&lt;" in unescaped or "&gt;" in unescaped or "&quot;" in unescaped or "&#39;" in unescaped or "&amp;" in unescaped:
        unescaped = html.unescape(unescaped)

    try:
        soup = BeautifulSoup(unescaped, "html.parser")
        for tag in soup.find_all(["p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"]):
            tag.append("\n")
        clean_text = soup.get_text(separator="\n", strip=True)
    except Exception:
        clean_text = unescaped

    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    return clean_text.strip()


from .portal_registry import classify_portal_from_url, extract_board_token

_CRAWLER_REGISTRY: Dict[str, Type[Any]] = {}


def register_crawler(name: str) -> Callable:
    """Decorator to register a crawler class in the centralized crawler registry."""
    def decorator(cls: Type[Any]) -> Type[Any]:
        _CRAWLER_REGISTRY[name.lower().strip()] = cls
        return cls
    return decorator


@register_crawler("greenhouse")
class GreenhouseCrawler:
    """Crawler for Greenhouse public job board REST API."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str, company_name: Optional[str] = None) -> List[JobPosting]:
        """Fetch all public jobs from Greenhouse board."""
        company = company_name or board_token.replace("-", " ").replace("_", " ").title()
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        jobs: List[JobPosting] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

            raw_jobs = data.get("jobs", [])
            for item in raw_jobs:
                job_id = f"gh_{board_token}_{item.get('id')}"
                title = item.get("title", "Software Engineer")
                job_url = item.get("absolute_url") or f"https://boards.greenhouse.io/{board_token}/jobs/{item.get('id')}"

                loc_data = item.get("location", {})
                location = loc_data.get("name") if isinstance(loc_data, dict) else str(loc_data) if loc_data else None
                clean_desc = clean_html_description(item.get("content", ""))
                posted_at = parse_job_posted_date(item.get("updated_at") or item.get("created_at") or item.get("first_published_at"))

                jobs.append(
                    JobPosting(
                        id=job_id,
                        company=company,
                        title=title,
                        url=job_url,
                        portal_type="greenhouse",
                        source="greenhouse_api",
                        status=JobStatus.DISCOVERED,
                        location=location,
                        description=clean_desc,
                        posted_at=posted_at,
                        raw_data=item,
                    )
                )
        except Exception as exc:
            log.warning("Greenhouse crawl failed for board %s: %s", board_token, exc)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="crawler",
                    component="greenhouse_crawler",
                    error_type="HTTP_ERROR",
                    message=f"Greenhouse crawl failed for board {board_token}: {exc}",
                    company=company_name or board_token,
                    portal_type="greenhouse",
                    board_token=board_token,
                    http_status=getattr(exc, "response", None) and getattr(exc.response, "status_code", None),
                )
            except Exception:
                pass

        return jobs

    async def async_crawl(
        self,
        board_token: str,
        company_name: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch all public jobs from Greenhouse board asynchronously."""
        company = company_name or board_token.replace("-", " ").replace("_", " ").title()
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        jobs: List[JobPosting] = []

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(url)
                resp.raise_for_status()
                data = resp.json()

                raw_jobs = data.get("jobs", [])
                for item in raw_jobs:
                    job_id = f"gh_{board_token}_{item.get('id')}"
                    title = item.get("title", "Software Engineer")
                    job_url = item.get("absolute_url") or f"https://boards.greenhouse.io/{board_token}/jobs/{item.get('id')}"

                    loc_data = item.get("location", {})
                    location = loc_data.get("name") if isinstance(loc_data, dict) else str(loc_data) if loc_data else None
                    clean_desc = clean_html_description(item.get("content", ""))
                    posted_at = parse_job_posted_date(item.get("updated_at") or item.get("created_at") or item.get("first_published_at"))

                    jobs.append(
                        JobPosting(
                            id=job_id,
                            company=company,
                            title=title,
                            url=job_url,
                            portal_type="greenhouse",
                            source="greenhouse_api",
                            status=JobStatus.DISCOVERED,
                            location=location,
                            description=clean_desc,
                            posted_at=posted_at,
                            raw_data=item,
                        )
                    )
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Greenhouse async crawl failed for board %s: %s", board_token, exc)

        return jobs


@register_crawler("lever")
class LeverCrawler:
    """Crawler for Lever public job postings REST API."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str, company_name: Optional[str] = None) -> List[JobPosting]:
        """Fetch all public postings from Lever board."""
        company = company_name or board_token.replace("-", " ").replace("_", " ").title()
        url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
        jobs: List[JobPosting] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

            for item in data:
                job_id = f"lever_{board_token}_{item.get('id')}"
                title = item.get("text", "Software Engineer")
                job_url = item.get("hostedUrl") or item.get("applyUrl") or f"https://jobs.lever.co/{board_token}/{item.get('id')}"

                cats = item.get("categories", {})
                location = cats.get("location") if isinstance(cats, dict) else None
                desc_text = item.get("descriptionPlain") or clean_html_description(item.get("description", ""))
                posted_at = parse_job_posted_date(item.get("createdAt"))

                jobs.append(
                    JobPosting(
                        id=job_id,
                        company=company,
                        title=title,
                        url=job_url,
                        portal_type="lever",
                        source="lever_api",
                        status=JobStatus.DISCOVERED,
                        location=location,
                        description=desc_text,
                        posted_at=posted_at,
                        raw_data=item,
                    )
                )
        except Exception as exc:
            log.warning("Lever crawl failed for board %s: %s", board_token, exc)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="crawler",
                    component="lever_crawler",
                    error_type="HTTP_ERROR",
                    message=f"Lever crawl failed for board {board_token}: {exc}",
                    company=company_name or board_token,
                    portal_type="lever",
                    board_token=board_token,
                    http_status=getattr(exc, "response", None) and getattr(exc.response, "status_code", None),
                )
            except Exception:
                pass

        return jobs

    async def async_crawl(
        self,
        board_token: str,
        company_name: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch all public postings from Lever board asynchronously."""
        company = company_name or board_token.replace("-", " ").replace("_", " ").title()
        url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
        jobs: List[JobPosting] = []

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(url)
                resp.raise_for_status()
                data = resp.json()

                for item in data:
                    job_id = f"lever_{board_token}_{item.get('id')}"
                    title = item.get("text", "Software Engineer")
                    job_url = item.get("hostedUrl") or item.get("applyUrl") or f"https://jobs.lever.co/{board_token}/{item.get('id')}"

                    cats = item.get("categories", {})
                    location = cats.get("location") if isinstance(cats, dict) else None
                    desc_text = item.get("descriptionPlain") or clean_html_description(item.get("description", ""))
                    posted_at = parse_job_posted_date(item.get("createdAt"))

                    jobs.append(
                        JobPosting(
                            id=job_id,
                            company=company,
                            title=title,
                            url=job_url,
                            portal_type="lever",
                            source="lever_api",
                            status=JobStatus.DISCOVERED,
                            location=location,
                            description=desc_text,
                            posted_at=posted_at,
                            raw_data=item,
                        )
                    )
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Lever async crawl failed for board %s: %s", board_token, exc)

        return jobs


@register_crawler("ashby")
class AshbyCrawler:
    """Crawler for Ashby public job board GraphQL & REST APIs."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str, company_name: Optional[str] = None) -> List[JobPosting]:
        """Fetch public postings from Ashby board."""
        company = company_name or board_token.replace("-", " ").replace("_", " ").title()
        jobs: List[JobPosting] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                # 1. Try GraphQL endpoint
                graphql_url = "https://jobs.ashbyhq.com/api/non-app-graphql-endpoint"
                query = {
                    "operationName": "ApiJobBoardWithTeams",
                    "variables": {"organizationHostedJobsPageName": board_token},
                    "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { jobPostings { id title locationName isRemote descriptionHtml publishedAt } } }",
                }
                try:
                    resp = client.post(graphql_url, json=query)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_postings = data.get("data", {}).get("jobBoard", {}).get("jobPostings", [])
                        if raw_postings:
                            for item in raw_postings:
                                posting_id = item.get("id")
                                job_id = f"ashby_{board_token}_{posting_id}"
                                title = item.get("title", "Software Engineer")
                                job_url = f"https://jobs.ashbyhq.com/{board_token}/{posting_id}"
                                loc = item.get("locationName")
                                desc = clean_html_description(item.get("descriptionHtml") or "")
                                posted_at = parse_job_posted_date(item.get("publishedAt") or item.get("updatedAt"))
                                jobs.append(
                                    JobPosting(
                                        id=job_id,
                                        company=company,
                                        title=title,
                                        url=job_url,
                                        portal_type="ashby",
                                        source="ashby_api",
                                        status=JobStatus.DISCOVERED,
                                        location=loc,
                                        description=desc,
                                        posted_at=posted_at,
                                        raw_data=item,
                                    )
                                )
                            return jobs
                except Exception:
                    pass

                # 2. Try REST posting-api endpoint
                api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}?includeCompensation=true"
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("jobs", []) or data.get("results", []):
                        posting_id = item.get("id")
                        job_id = f"ashby_{board_token}_{posting_id}"
                        title = item.get("title", "Software Engineer")
                        job_url = item.get("jobUrl") or f"https://jobs.ashbyhq.com/{board_token}/{posting_id}"
                        location = item.get("location")
                        desc = clean_html_description(item.get("descriptionHtml") or item.get("descriptionPlain") or "")
                        posted_at = parse_job_posted_date(item.get("publishedAt") or item.get("updatedAt"))
                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type="ashby",
                                source="ashby_api",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=desc,
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )
        except Exception as exc:
            log.warning("Ashby crawl failed for board %s: %s", board_token, exc)

        return jobs

    async def async_crawl(
        self,
        board_token: str,
        company_name: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch public postings from Ashby board asynchronously."""
        company = company_name or board_token.replace("-", " ").replace("_", " ").title()
        jobs: List[JobPosting] = []

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                graphql_url = "https://jobs.ashbyhq.com/api/non-app-graphql-endpoint"
                query = {
                    "operationName": "ApiJobBoardWithTeams",
                    "variables": {"organizationHostedJobsPageName": board_token},
                    "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { jobPostings { id title locationName isRemote descriptionHtml publishedAt } } }",
                }
                try:
                    resp = await local_client.post(graphql_url, json=query)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_postings = data.get("data", {}).get("jobBoard", {}).get("jobPostings", [])
                        if raw_postings:
                            for item in raw_postings:
                                posting_id = item.get("id")
                                job_id = f"ashby_{board_token}_{posting_id}"
                                title = item.get("title", "Software Engineer")
                                job_url = f"https://jobs.ashbyhq.com/{board_token}/{posting_id}"
                                loc = item.get("locationName")
                                desc = clean_html_description(item.get("descriptionHtml") or "")
                                posted_at = parse_job_posted_date(item.get("publishedAt") or item.get("updatedAt"))
                                jobs.append(
                                    JobPosting(
                                        id=job_id,
                                        company=company,
                                        title=title,
                                        url=job_url,
                                        portal_type="ashby",
                                        source="ashby_api",
                                        status=JobStatus.DISCOVERED,
                                        location=loc,
                                        description=desc,
                                        posted_at=posted_at,
                                        raw_data=item,
                                    )
                                )
                            return jobs
                except Exception:
                    pass

                api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}?includeCompensation=true"
                resp = await local_client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("jobs", []) or data.get("results", []):
                        posting_id = item.get("id")
                        job_id = f"ashby_{board_token}_{posting_id}"
                        title = item.get("title", "Software Engineer")
                        job_url = item.get("jobUrl") or f"https://jobs.ashbyhq.com/{board_token}/{posting_id}"
                        location = item.get("location")
                        desc = clean_html_description(item.get("descriptionHtml") or item.get("descriptionPlain") or "")
                        posted_at = parse_job_posted_date(item.get("publishedAt") or item.get("updatedAt"))
                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type="ashby",
                                source="ashby_api",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=desc,
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Ashby async crawl failed for board %s: %s", board_token, exc)

        return jobs


@register_crawler("smartrecruiters")
class SmartRecruitersCrawler:
    """Crawler for SmartRecruiters public posting REST API."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str, company_name: Optional[str] = None) -> List[JobPosting]:
        """Fetch all public job postings from SmartRecruiters company board with pagination."""
        company = company_name or board_token.replace("-", " ").replace("_", " ").title()
        page_size = 100
        max_pages = 10
        jobs: List[JobPosting] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                for page in range(max_pages):
                    offset = page * page_size
                    url = f"https://api.smartrecruiters.com/v1/companies/{board_token}/postings?limit={page_size}&offset={offset}&status=PUBLIC"
                    resp = client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                    items = data.get("content", []) if isinstance(data, dict) else []
                    if not items:
                        break

                    for item in items:
                        posting_id = str(item.get("id", ""))
                        job_id = f"sr_{board_token}_{posting_id}"
                        title = item.get("name", "Software Engineer")
                        job_url = f"https://jobs.smartrecruiters.com/{board_token}/{posting_id}"

                        loc = item.get("location", {})
                        city = loc.get("city", "")
                        region = loc.get("region", "")
                        country = loc.get("country", "").upper()
                        location = f"{city}, {region} ({country})" if city and region else city or country or "United States"

                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type="smartrecruiters",
                                source="smartrecruiters_api",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=f"SmartRecruiters posting {title} at {company}",
                                raw_data=item,
                            )
                        )

                    if len(items) < page_size:
                        break
        except Exception as exc:
            log.warning("SmartRecruiters crawl failed for %s: %s", board_token, exc)

        return jobs

    async def async_crawl(
        self,
        board_token: str,
        company_name: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch public job postings from SmartRecruiters company board asynchronously."""
        company = company_name or board_token.replace("-", " ").replace("_", " ").title()
        page_size = 100
        max_pages = 10
        jobs: List[JobPosting] = []

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                for page in range(max_pages):
                    offset = page * page_size
                    url = f"https://api.smartrecruiters.com/v1/companies/{board_token}/postings?limit={page_size}&offset={offset}&status=PUBLIC"
                    resp = await local_client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                    items = data.get("content", []) if isinstance(data, dict) else []
                    if not items:
                        break

                    for item in items:
                        posting_id = str(item.get("id", ""))
                        job_id = f"sr_{board_token}_{posting_id}"
                        title = item.get("name", "Software Engineer")
                        job_url = f"https://jobs.smartrecruiters.com/{board_token}/{posting_id}"

                        loc = item.get("location", {})
                        city = loc.get("city", "")
                        region = loc.get("region", "")
                        country = loc.get("country", "").upper()
                        location = f"{city}, {region} ({country})" if city and region else city or country or "United States"

                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type="smartrecruiters",
                                source="smartrecruiters_api",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=f"SmartRecruiters posting {title} at {company}",
                                raw_data=item,
                            )
                        )

                    if len(items) < page_size:
                        break
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("SmartRecruiters async crawl failed for %s: %s", board_token, exc)

        return jobs


@register_crawler("echojobs")
class EchoJobsFeeder:
    """High-volume zero-auth aggregator feeder streaming verified SWE postings with direct ATS URLs."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def fetch_jobs(self, max_pages: int = 10) -> List[JobPosting]:
        """Fetch software engineering jobs from EchoJobs feed across pages."""
        jobs: List[JobPosting] = []
        base_url = "https://echojobs.io/api/jobs"

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                for page in range(1, max_pages + 1):
                    url = f"{base_url}?page={page}&per_page=100"
                    resp = client.get(url)
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    items = data.get("data", []) if isinstance(data, dict) else data if isinstance(data, list) else []
                    if not items:
                        break

                    for item in items:
                        posting_id = str(item.get("id", ""))
                        job_id = f"echo_{posting_id}"
                        title = item.get("title", "Software Engineer")
                        company = item.get("organization_name") or item.get("company_name") or "Tech Company"
                        job_url = item.get("url") or item.get("application_url") or item.get("job_url") or ""
                        if not job_url:
                            continue

                        locs = item.get("locations", [])
                        location = ", ".join(locs) if isinstance(locs, list) else str(locs) if locs else "United States"
                        portal_type = classify_portal_from_url(job_url)

                        posted_at = parse_job_posted_date(item.get("created_at") or item.get("published_at"))

                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type=portal_type,
                                source="echojobs_feeder",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=f"Software engineering role {title} at {company}",
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )
        except Exception as exc:
            log.warning("EchoJobs feeder fetch failed: %s", exc)

        return jobs

    async def async_fetch_jobs(
        self,
        max_pages: int = 10,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch software engineering jobs from EchoJobs feed asynchronously."""
        jobs: List[JobPosting] = []
        base_url = "https://echojobs.io/api/jobs"

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                for page in range(1, max_pages + 1):
                    url = f"{base_url}?page={page}&per_page=100"
                    resp = await local_client.get(url)
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    items = data.get("data", []) if isinstance(data, dict) else data if isinstance(data, list) else []
                    if not items:
                        break

                    for item in items:
                        posting_id = str(item.get("id", ""))
                        job_id = f"echo_{posting_id}"
                        title = item.get("title", "Software Engineer")
                        company = item.get("organization_name") or item.get("company_name") or "Tech Company"
                        job_url = item.get("url") or item.get("application_url") or item.get("job_url") or ""
                        if not job_url:
                            continue

                        locs = item.get("locations", [])
                        location = ", ".join(locs) if isinstance(locs, list) else str(locs) if locs else "United States"
                        portal_type = classify_portal_from_url(job_url)
                        posted_at = parse_job_posted_date(item.get("created_at") or item.get("published_at"))

                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type=portal_type,
                                source="echojobs_feeder",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=f"Software engineering role {title} at {company}",
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("EchoJobs async feeder fetch failed: %s", exc)

        return jobs


@register_crawler("amazon")
class AmazonCrawler:
    """Crawler for Amazon.jobs public career search API."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str = "amazon", company_name: str = "Amazon") -> List[JobPosting]:
        """Fetch software development postings from Amazon.jobs API."""
        url = "https://www.amazon.jobs/en/search.json?category[]=software-development&country[]=USA&result_type=jobs"
        jobs: List[JobPosting] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

            for item in data.get("jobs", []):
                icims_id = item.get("id_icims") or item.get("id")
                job_id = f"amazon_{icims_id}"
                title = item.get("title", "Software Development Engineer")
                job_path = item.get("job_path", "")
                job_url = f"https://www.amazon.jobs{job_path}" if job_path else f"https://www.amazon.jobs/en/jobs/{icims_id}"

                city = item.get("city", "")
                state = item.get("state", "")
                country = item.get("country_code", "USA")
                location = f"{city}, {state} ({country})" if city and state else country

                clean_desc = clean_html_description(item.get("description", ""))
                posted_at = parse_job_posted_date(item.get("posted_date"))

                jobs.append(
                    JobPosting(
                        id=job_id,
                        company=company_name,
                        title=title,
                        url=job_url,
                        portal_type="amazon",
                        source="amazon_api",
                        status=JobStatus.DISCOVERED,
                        location=location,
                        description=clean_desc,
                        posted_at=posted_at,
                        raw_data=item,
                    )
                )
        except Exception as exc:
            log.warning("Amazon crawl failed: %s", exc)

        return jobs

    async def async_crawl(
        self,
        board_token: str = "amazon",
        company_name: str = "Amazon",
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch software development postings from Amazon.jobs API asynchronously."""
        url = "https://www.amazon.jobs/en/search.json?category[]=software-development&country[]=USA&result_type=jobs"
        jobs: List[JobPosting] = []

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(url)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("jobs", []):
                    icims_id = item.get("id_icims") or item.get("id")
                    job_id = f"amazon_{icims_id}"
                    title = item.get("title", "Software Development Engineer")
                    job_path = item.get("job_path", "")
                    job_url = f"https://www.amazon.jobs{job_path}" if job_path else f"https://www.amazon.jobs/en/jobs/{icims_id}"

                    city = item.get("city", "")
                    state = item.get("state", "")
                    country = item.get("country_code", "USA")
                    location = f"{city}, {state} ({country})" if city and state else country

                    clean_desc = clean_html_description(item.get("description", ""))
                    posted_at = parse_job_posted_date(item.get("posted_date"))

                    jobs.append(
                        JobPosting(
                            id=job_id,
                            company=company_name,
                            title=title,
                            url=job_url,
                            portal_type="amazon",
                            source="amazon_api",
                            status=JobStatus.DISCOVERED,
                            location=location,
                            description=clean_desc,
                            posted_at=posted_at,
                            raw_data=item,
                        )
                    )
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Amazon async crawl failed: %s", exc)

        return jobs


@register_crawler("microsoft")
class MicrosoftCrawler:
    """Crawler for Microsoft Careers public search API."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str = "microsoft", company_name: str = "Microsoft") -> List[JobPosting]:
        """Fetch Software Engineering postings from Microsoft Careers API with pagination."""
        page_size = 50
        max_pages = 10
        jobs: List[JobPosting] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                for page in range(1, max_pages + 1):
                    url = f"https://gcsservices.careers.microsoft.com/search/api/v1/search?q=Software%20Engineer&l=en_us&pg={page}&pgSz={page_size}&flt=true&exp=true&country=United%20States"
                    resp = client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                    items = data.get("data", {}).get("jobs", []) if isinstance(data, dict) else []
                    if not items:
                        break

                    for item in items:
                        job_id_val = item.get("jobId")
                        job_id = f"msft_{job_id_val}"
                        title = item.get("title", "Software Engineer")
                        job_url = f"https://jobs.careers.microsoft.com/global/en/job/{job_id_val}"

                        props = item.get("properties", {})
                        location = props.get("primaryLocation", "United States")
                        clean_desc = clean_html_description(props.get("description", ""))
                        posted_at = parse_job_posted_date(props.get("postingDate") or item.get("postingDate"))

                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company_name,
                                title=title,
                                url=job_url,
                                portal_type="microsoft",
                                source="microsoft_api",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=clean_desc,
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )

                    if len(items) < page_size:
                        break
        except Exception as exc:
            log.warning("Microsoft crawl failed: %s", exc)

        return jobs

    async def async_crawl(
        self,
        board_token: str = "microsoft",
        company_name: str = "Microsoft",
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch Software Engineering postings from Microsoft Careers API asynchronously."""
        page_size = 50
        max_pages = 10
        jobs: List[JobPosting] = []

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                for page in range(1, max_pages + 1):
                    url = f"https://gcsservices.careers.microsoft.com/search/api/v1/search?q=Software%20Engineer&l=en_us&pg={page}&pgSz={page_size}&flt=true&exp=true&country=United%20States"
                    resp = await local_client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                    items = data.get("data", {}).get("jobs", []) if isinstance(data, dict) else []
                    if not items:
                        break

                    for item in items:
                        job_id_val = item.get("jobId")
                        job_id = f"msft_{job_id_val}"
                        title = item.get("title", "Software Engineer")
                        job_url = f"https://jobs.careers.microsoft.com/global/en/job/{job_id_val}"

                        props = item.get("properties", {})
                        location = props.get("primaryLocation", "United States")
                        clean_desc = clean_html_description(props.get("description", ""))
                        posted_at = parse_job_posted_date(props.get("postingDate") or item.get("postingDate"))

                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company_name,
                                title=title,
                                url=job_url,
                                portal_type="microsoft",
                                source="microsoft_api",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=clean_desc,
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )

                    if len(items) < page_size:
                        break
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Microsoft async crawl failed: %s", exc)

        return jobs


@register_crawler("google")
class GoogleCareersCrawler:
    """Crawler for Google Careers public search endpoint."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str = "google", company_name: str = "Google") -> List[JobPosting]:
        """Fetch Software Engineering postings from Google Careers with pagination."""
        page_size = 50
        max_pages = 10
        jobs: List[JobPosting] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                for page in range(1, max_pages + 1):
                    url = f"https://careers.google.com/api/v3/search/?q=Software%20Engineer&location=United%20States&page_size={page_size}&page={page}"
                    resp = client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                    items = data.get("jobs", [])
                    if not items:
                        break

                    for item in items:
                        job_id_val = item.get("id")
                        job_id = f"google_{job_id_val}"
                        title = item.get("title", "Software Engineer")
                        job_url = item.get("apply_url") or f"https://careers.google.com/jobs/results/{job_id_val}"

                        loc_list = item.get("locations", [])
                        location = loc_list[0].get("display") if loc_list else "United States"
                        clean_desc = clean_html_description(item.get("description", ""))
                        posted_at = parse_job_posted_date(item.get("publish_date") or item.get("created"))

                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company_name,
                                title=title,
                                url=job_url,
                                portal_type="google",
                                source="google_api",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=clean_desc,
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )

                    if len(items) < page_size:
                        break
        except Exception as exc:
            log.warning("Google crawl failed: %s", exc)

        return jobs

    async def async_crawl(
        self,
        board_token: str = "google",
        company_name: str = "Google",
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch Software Engineering postings from Google Careers asynchronously."""
        page_size = 50
        max_pages = 10
        jobs: List[JobPosting] = []

        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                for page in range(1, max_pages + 1):
                    url = f"https://careers.google.com/api/v3/search/?q=Software%20Engineer&location=United%20States&page_size={page_size}&page={page}"
                    resp = await local_client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                    items = data.get("jobs", [])
                    if not items:
                        break

                    for item in items:
                        job_id_val = item.get("id")
                        job_id = f"google_{job_id_val}"
                        title = item.get("title", "Software Engineer")
                        job_url = item.get("apply_url") or f"https://careers.google.com/jobs/results/{job_id_val}"

                        loc_list = item.get("locations", [])
                        location = loc_list[0].get("display") if loc_list else "United States"
                        clean_desc = clean_html_description(item.get("description", ""))
                        posted_at = parse_job_posted_date(item.get("publish_date") or item.get("created"))

                        jobs.append(
                            JobPosting(
                                id=job_id,
                                company=company_name,
                                title=title,
                                url=job_url,
                                portal_type="google",
                                source="google_api",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description=clean_desc,
                                posted_at=posted_at,
                                raw_data=item,
                            )
                        )

                    if len(items) < page_size:
                        break
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Google async crawl failed: %s", exc)

        return jobs


KNOWN_WORKDAY_SLUGS = {
    "adobe": ["adobe", "AdobeCareers", "external"],
    "capitalone": ["Capital_One_Careers", "External_Career_Site", "capitalone"],
    "cisco": ["Cisco_Careers", "External_Career_Site", "cisco"],
    "crowdstrike": ["crowdstrike_careers", "CrowdStrike", "crowdstrike"],
    "nvidia": ["NVIDIAExternalCareerSite", "nvidia", "careers"],
    "salesforce": ["External_Career_Site", "Salesforce_Careers", "salesforce"],
    "target": ["targetcareers", "External_Career_Site", "target"],
    "walmart": ["walmart_careers", "External_Career_Site", "walmart"],
}


@register_crawler("workday")
class WorkdayCrawler:
    """Crawler for Workday public enterprise CXS search endpoints (*.myworkdayjobs.com)."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def crawl(
        self,
        tenant: str = "capitalone",
        company_name: Optional[str] = None,
        board: Optional[str] = None,
        board_token: Optional[str] = None,
        careers_url: Optional[str] = None,
    ) -> List[JobPosting]:
        """Fetch jobs from Workday public CXS endpoint."""
        return asyncio.run(
            self.async_crawl(
                tenant=tenant,
                company_name=company_name,
                board=board,
                board_token=board_token,
                careers_url=careers_url,
            )
        )

    async def async_crawl(
        self,
        tenant: str = "capitalone",
        company_name: Optional[str] = None,
        board: Optional[str] = None,
        board_token: Optional[str] = None,
        careers_url: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch jobs from Workday public CXS endpoint asynchronously with dynamic slug resolution."""
        token = board_token or tenant
        b_name = board or token
        company = company_name or token.replace("-", " ").replace("_", " ").title()

        wd_instance = "wd1"
        if careers_url and "myworkdayjobs.com" in careers_url:
            match = re.search(r"https://([a-zA-Z0-9_-]+)\.(wd\d+\.)?myworkdayjobs\.com/([a-zA-Z0-9_-]+)", careers_url)
            if match:
                token = match.group(1)
                if match.group(2):
                    wd_instance = match.group(2).rstrip(".")
                b_name = match.group(3)

        # Build candidate career site slugs
        raw_slugs = [b_name] + KNOWN_WORKDAY_SLUGS.get(token.lower(), []) + ["External_Career_Site", "careers", "external", f"{token}_careers"]
        candidate_slugs: List[str] = []
        for s in raw_slugs:
            if s and s not in candidate_slugs:
                candidate_slugs.append(s)

        page_size = 50
        max_pages = 10
        jobs: List[JobPosting] = []

        local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
        try:
            resolved_slug: Optional[str] = None

            # 1. Resolve working slug
            for slug in candidate_slugs:
                test_url = f"https://{token}.{wd_instance}.myworkdayjobs.com/wday/cxs/{token}/{slug}/jobs"
                payload = {"appliedFacets": {}, "limit": page_size, "offset": 0, "searchText": ""}
                try:
                    resp = await local_client.post(test_url, json=payload)
                    if resp.status_code == 200:
                        resolved_slug = slug
                        data = resp.json()
                        items = data.get("jobPostings", [])
                        for item in items:
                            bullet_fields = item.get("bulletFields", [])
                            ext_path = item.get("externalPath", "")
                            posting_id = bullet_fields[0] if bullet_fields else ext_path.split("_")[-1] if "_" in ext_path else str(hash(ext_path))
                            job_id = f"workday_{token}_{posting_id}"
                            title = item.get("title", "Software Engineer")
                            job_url = f"https://{token}.{wd_instance}.myworkdayjobs.com/en-US/{slug}{ext_path}"
                            location = item.get("locationsText", "United States")

                            posted_str = item.get("postedOn")
                            if not posted_str:
                                for field in bullet_fields:
                                    if isinstance(field, str) and ("post" in field.lower() or "ago" in field.lower() or "today" in field.lower() or "yesterday" in field.lower()):
                                        posted_str = field
                                        break
                            posted_at = parse_job_posted_date(posted_str)

                            jobs.append(
                                JobPosting(
                                    id=job_id,
                                    company=company,
                                    title=title,
                                    url=job_url,
                                    portal_type="workday",
                                    source="workday_api",
                                    status=JobStatus.DISCOVERED,
                                    location=location,
                                    description=f"Workday posting {title} at {company}",
                                    posted_at=posted_at,
                                    raw_data=item,
                                )
                            )
                        break
                except Exception:
                    continue

            # 2. Paginate remaining pages if first page yielded full batch
            if resolved_slug and len(jobs) >= page_size:
                for page in range(1, max_pages):
                    offset = page * page_size
                    url = f"https://{token}.{wd_instance}.myworkdayjobs.com/wday/cxs/{token}/{resolved_slug}/jobs"
                    payload = {"appliedFacets": {}, "limit": page_size, "offset": offset, "searchText": ""}
                    try:
                        resp = await local_client.post(url, json=payload)
                        if resp.status_code != 200:
                            break
                        data = resp.json()
                        items = data.get("jobPostings", [])
                        if not items:
                            break
                        for item in items:
                            bullet_fields = item.get("bulletFields", [])
                            ext_path = item.get("externalPath", "")
                            posting_id = bullet_fields[0] if bullet_fields else ext_path.split("_")[-1] if "_" in ext_path else str(hash(ext_path))
                            job_id = f"workday_{token}_{posting_id}"
                            title = item.get("title", "Software Engineer")
                            job_url = f"https://{token}.{wd_instance}.myworkdayjobs.com/en-US/{resolved_slug}{ext_path}"
                            location = item.get("locationsText", "United States")
                            posted_at = parse_job_posted_date(item.get("postedOn"))

                            jobs.append(
                                JobPosting(
                                    id=job_id,
                                    company=company,
                                    title=title,
                                    url=job_url,
                                    portal_type="workday",
                                    source="workday_api",
                                    status=JobStatus.DISCOVERED,
                                    location=location,
                                    description=f"Workday posting {title} at {company}",
                                    posted_at=posted_at,
                                    raw_data=item,
                                )
                            )
                        if len(items) < page_size:
                            break
                    except Exception:
                        break
        finally:
            if client is None:
                await local_client.aclose()

        return jobs


@register_crawler("icims")
class ICIMSCrawler:
    """Crawler for enterprise iCIMS career portals."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str, company_name: Optional[str] = None) -> List[JobPosting]:
        """Fetch jobs from iCIMS portal synchronously."""
        return asyncio.run(self.async_crawl(board_token=board_token, company_name=company_name))

    async def async_crawl(
        self,
        board_token: str,
        company_name: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch jobs from iCIMS portal asynchronously."""
        company = company_name or board_token.title()
        jobs: List[JobPosting] = []
        url = f"https://careers-{board_token}.icims.com/jobs/search?in_iframe=1"
        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for row in soup.find_all("div", class_="row"):
                        link = row.find("a")
                        if not link:
                            continue
                        title = link.get_text().strip()
                        job_url = link.get("href", "")
                        if not job_url or not title:
                            continue
                        posting_id = str(hash(job_url))
                        jobs.append(
                            JobPosting(
                                id=f"icims_{board_token}_{posting_id}",
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type="icims",
                                source="icims_crawler",
                                status=JobStatus.DISCOVERED,
                                location="United States",
                                description="",
                            )
                        )
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("iCIMS crawl failed for %s: %s", board_token, exc)
        return jobs


@register_crawler("taleo")
class TaleoCrawler:
    """Crawler for Oracle Taleo enterprise career portals."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str, company_name: Optional[str] = None) -> List[JobPosting]:
        """Fetch jobs from Taleo portal synchronously."""
        return asyncio.run(self.async_crawl(board_token=board_token, company_name=company_name))

    async def async_crawl(
        self,
        board_token: str,
        company_name: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch jobs from Taleo portal asynchronously."""
        company = company_name or board_token.title()
        jobs: List[JobPosting] = []
        url = f"https://{board_token}.taleo.net/careersection/api/search"
        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    requisitions = data.get("requisitions", []) if isinstance(data, dict) else []
                    for req in requisitions:
                        title = req.get("jobTitle") or req.get("title", "Software Engineer")
                        posting_id = str(req.get("contestNo") or req.get("id", hash(title)))
                        job_url = req.get("jobUrl") or f"https://{board_token}.taleo.net/careersection/jobdetail.ftl?job={posting_id}"
                        desc = clean_html_description(req.get("description", ""))
                        jobs.append(
                            JobPosting(
                                id=f"taleo_{board_token}_{posting_id}",
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type="taleo",
                                source="taleo_crawler",
                                status=JobStatus.DISCOVERED,
                                location="United States",
                                description=desc,
                            )
                        )
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Taleo crawl failed for %s: %s", board_token, exc)
        return jobs


@register_crawler("bamboohr")
class BambooHRCrawler:
    """Crawler for BambooHR public job boards."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def crawl(self, board_token: str, company_name: Optional[str] = None) -> List[JobPosting]:
        """Fetch jobs from BambooHR board synchronously."""
        return asyncio.run(self.async_crawl(board_token=board_token, company_name=company_name))

    async def async_crawl(
        self,
        board_token: str,
        company_name: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Fetch jobs from BambooHR board asynchronously."""
        company = company_name or board_token.title()
        jobs: List[JobPosting] = []
        url = f"https://{board_token}.bamboohr.com/careers/list"
        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("result", []) if isinstance(data, dict) else []
                    for item in result:
                        title = item.get("jobOpeningName", "Software Engineer")
                        posting_id = str(item.get("id", hash(title)))
                        job_url = f"https://{board_token}.bamboohr.com/careers/{posting_id}"
                        location = item.get("location", {}).get("city", "United States") if isinstance(item.get("location"), dict) else "United States"
                        jobs.append(
                            JobPosting(
                                id=f"bamboo_{board_token}_{posting_id}",
                                company=company,
                                title=title,
                                url=job_url,
                                portal_type="bamboohr",
                                source="bamboohr_crawler",
                                status=JobStatus.DISCOVERED,
                                location=location,
                                description="",
                            )
                        )
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("BambooHR crawl failed for %s: %s", board_token, exc)
        return jobs


class PortalCrawler:
    """Unified portal crawler dispatcher supporting Greenhouse, Lever, Ashby, SmartRecruiters, Amazon, Microsoft, Google, Workday, iCIMS, Taleo, BambooHR."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.greenhouse_crawler = GreenhouseCrawler(timeout=timeout)
        self.lever_crawler = LeverCrawler(timeout=timeout)
        self.ashby_crawler = AshbyCrawler(timeout=timeout)
        self.smartrecruiters_crawler = SmartRecruitersCrawler(timeout=timeout)
        self.echojobs_feeder = EchoJobsFeeder(timeout=timeout)
        self.amazon_crawler = AmazonCrawler(timeout=timeout)
        self.microsoft_crawler = MicrosoftCrawler(timeout=timeout)
        self.google_crawler = GoogleCareersCrawler(timeout=timeout)
        self.workday_crawler = WorkdayCrawler(timeout=timeout)
        self.icims_crawler = ICIMSCrawler(timeout=timeout)
        self.taleo_crawler = TaleoCrawler(timeout=timeout)
        self.bamboohr_crawler = BambooHRCrawler(timeout=timeout)

    def crawl(
        self,
        portal_type: str,
        board_token: str,
        company_name: Optional[str] = None,
        careers_url: Optional[str] = None,
    ) -> List[JobPosting]:
        """Dispatch synchronous crawling to the matching portal crawler."""
        portal = portal_type.lower().strip()
        if portal == "greenhouse":
            return self.greenhouse_crawler.crawl(board_token=board_token, company_name=company_name)
        elif portal == "lever":
            return self.lever_crawler.crawl(board_token=board_token, company_name=company_name)
        elif portal == "ashby":
            return self.ashby_crawler.crawl(board_token=board_token, company_name=company_name)
        elif portal == "smartrecruiters":
            return self.smartrecruiters_crawler.crawl(board_token=board_token, company_name=company_name)
        elif portal == "echojobs":
            return self.echojobs_feeder.fetch_jobs(max_pages=2)
        elif portal == "amazon":
            return self.amazon_crawler.crawl(board_token=board_token, company_name=company_name or "Amazon")
        elif portal == "microsoft":
            return self.microsoft_crawler.crawl(board_token=board_token, company_name=company_name or "Microsoft")
        elif portal == "google":
            return self.google_crawler.crawl(board_token=board_token, company_name=company_name or "Google")
        elif portal == "workday":
            return self.workday_crawler.crawl(tenant=board_token, company_name=company_name, board_token=board_token, careers_url=careers_url)
        elif portal == "icims":
            return self.icims_crawler.crawl(board_token=board_token, company_name=company_name)
        elif portal == "taleo":
            return self.taleo_crawler.crawl(board_token=board_token, company_name=company_name)
        elif portal == "bamboohr":
            return self.bamboohr_crawler.crawl(board_token=board_token, company_name=company_name)
        else:
            log.warning("Unsupported automated crawler portal type: %s", portal_type)
            return []

    async def async_crawl(
        self,
        portal_type: str,
        board_token: str,
        company_name: Optional[str] = None,
        careers_url: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Dispatch asynchronous crawling to the matching portal crawler."""
        portal = portal_type.lower().strip()
        if portal == "greenhouse":
            return await self.greenhouse_crawler.async_crawl(board_token=board_token, company_name=company_name, client=client)
        elif portal == "lever":
            return await self.lever_crawler.async_crawl(board_token=board_token, company_name=company_name, client=client)
        elif portal == "ashby":
            return await self.ashby_crawler.async_crawl(board_token=board_token, company_name=company_name, client=client)
        elif portal == "smartrecruiters":
            return await self.smartrecruiters_crawler.async_crawl(board_token=board_token, company_name=company_name, client=client)
        elif portal == "echojobs":
            return await self.echojobs_feeder.async_fetch_jobs(max_pages=2, client=client)
        elif portal == "amazon":
            return await self.amazon_crawler.async_crawl(board_token=board_token, company_name=company_name or "Amazon", client=client)
        elif portal == "microsoft":
            return await self.microsoft_crawler.async_crawl(board_token=board_token, company_name=company_name or "Microsoft", client=client)
        elif portal == "google":
            return await self.google_crawler.async_crawl(board_token=board_token, company_name=company_name or "Google", client=client)
        elif portal == "workday":
            return await self.workday_crawler.async_crawl(tenant=board_token, company_name=company_name, board_token=board_token, careers_url=careers_url, client=client)
        elif portal == "icims":
            return await self.icims_crawler.async_crawl(board_token=board_token, company_name=company_name, client=client)
        elif portal == "taleo":
            return await self.taleo_crawler.async_crawl(board_token=board_token, company_name=company_name, client=client)
        elif portal == "bamboohr":
            return await self.bamboohr_crawler.async_crawl(board_token=board_token, company_name=company_name, client=client)
        else:
            log.warning("Unsupported automated crawler portal type: %s", portal_type)
            return []


class CrawlerRegistry:
    """Deferred crawler registry that lazily resolves and instantiates crawler tools on demand."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._instances: Dict[str, Any] = {}

    def get_crawler(self, portal_type: str) -> Any:
        """Lazily instantiate and return crawler tool by portal type."""
        pt = portal_type.lower().strip()
        if pt not in self._instances:
            cls = _CRAWLER_REGISTRY.get(pt)
            if cls:
                self._instances[pt] = cls(timeout=self.timeout)
            else:
                self._instances[pt] = GreenhouseCrawler(timeout=self.timeout)
        return self._instances[pt]

    def resolve_crawler(self, url_or_portal: str) -> Any:
        """Dynamically resolve crawler tool from URL domain or portal name."""
        if url_or_portal.startswith("http"):
            portal = classify_portal_from_url(url_or_portal)
        else:
            portal = url_or_portal
        return self.get_crawler(portal)

    def list_available_crawlers(self) -> List[str]:
        """Return list of supported crawler tool identifiers."""
        return list(_CRAWLER_REGISTRY.keys())
