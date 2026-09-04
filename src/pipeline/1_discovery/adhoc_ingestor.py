"""Ad-hoc single URL ingestion and HTML parser for JobPosting schemas."""

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import httpx

from src.core.models import JobPosting, JobStatus

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

PORTAL_PATTERNS = [
    (re.compile(r"(?:boards|job-boards)\.greenhouse\.io|gh_jid=", re.I), "greenhouse"),
    (re.compile(r"jobs\.lever\.co|lever\.co", re.I), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com|ashbyhq\.com", re.I), "ashby"),
    (re.compile(r"myworkdayjobs\.com|myworkday\.com", re.I), "workday"),
    (re.compile(r"smartrecruiters\.com", re.I), "smartrecruiters"),
    (re.compile(r"apply\.workable\.com", re.I), "workable"),
]


class AdhocIngestor:
    """Ingests single job posting URLs, auto-detects portal types, and extracts structured job info."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    @staticmethod
    def detect_portal(url: str) -> str:
        """Identify ATS or job board portal type from URL string."""
        for pattern, portal_name in PORTAL_PATTERNS:
            if pattern.search(url):
                return portal_name
        return "generic"

    @staticmethod
    def generate_job_id(url: str) -> str:
        """Create a stable job identifier from its URL."""
        return "job_" + hashlib.md5(url.encode("utf-8")).hexdigest()[:12]

    def extract_clean_text(self, html_content: str) -> str:
        """Strip boilerplate elements and extract readable text."""
        if not html_content or not html_content.strip():
            return ""

        soup = BeautifulSoup(html_content, "html.parser")

        # Decompose non-content tags
        for tag in soup(
            ["script", "style", "nav", "footer", "header", "noscript", "svg", "form", "button", "aside", "iframe"]
        ):
            tag.decompose()

        # Decompose noisy UI classes
        for tag in soup.find_all(
            class_=re.compile(
                r"(cookie|banner|nav|footer|header|menu|sidebar|modal|popup|consent|privacy-notice)",
                re.I,
            )
        ):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    def extract_json_ld(self, html_content: str) -> Optional[Dict[str, Any]]:
        """Locate and parse Schema.org JobPosting from JSON-LD script tags."""
        if not html_content:
            return None

        soup = BeautifulSoup(html_content, "html.parser")
        scripts = soup.find_all("script", type=lambda t: t and "ld+json" in t.lower())

        for script in scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string.strip())
                job_data = self._find_job_in_json_obj(data)
                if job_data:
                    return job_data
            except Exception as exc:
                log.debug("JSON-LD parsing error: %s", exc)
                continue

        return None

    def _find_job_in_json_obj(self, data: Any) -> Optional[Dict[str, Any]]:
        """Recursively find JobPosting schema object."""
        if isinstance(data, list):
            for item in data:
                res = self._find_job_in_json_obj(item)
                if res:
                    return res
            return None

        if isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                return self._find_job_in_json_obj(data["@graph"])

            type_val = data.get("@type", "")
            if isinstance(type_val, list):
                is_job = any(isinstance(t, str) and t.lower() == "jobposting" for t in type_val)
            elif isinstance(type_val, str):
                is_job = type_val.lower() == "jobposting"
            else:
                is_job = False

            if is_job:
                return data

        return None

    def _derive_company_name_from_url(self, url: str) -> str:
        """Derive fallback company name from domain or path."""
        parsed = urlparse(url)
        # Check path first for boards like boards.greenhouse.io/stripe or jobs.lever.co/stripe
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts and ("greenhouse.io" in parsed.netloc or "lever.co" in parsed.netloc or "ashbyhq.com" in parsed.netloc):
            return path_parts[0].replace("-", " ").replace("_", " ").title()

        domain = parsed.netloc.replace("www.", "").split(".")[0]
        return domain.replace("-", " ").replace("_", " ").title() if domain else "Unknown Company"

    def _parse_job_from_html(self, html_content: str, url: str) -> JobPosting:
        """Construct JobPosting model from HTML content using JSON-LD or DOM heuristics."""
        portal_type = self.detect_portal(url)
        job_id = self.generate_job_id(url)
        clean_text = self.extract_clean_text(html_content)

        # 1. Try JSON-LD parsing
        json_ld = self.extract_json_ld(html_content)
        if json_ld:
            title = json_ld.get("title") or json_ld.get("name") or "Software Engineer"
            
            # Company
            hiring_org = json_ld.get("hiringOrganization")
            company = ""
            if isinstance(hiring_org, dict):
                company = hiring_org.get("name") or ""
            elif isinstance(hiring_org, str):
                company = hiring_org
            if not company:
                company = self._derive_company_name_from_url(url)

            # Location
            location = None
            job_loc = json_ld.get("jobLocation")
            if isinstance(job_loc, dict):
                addr = job_loc.get("address")
                if isinstance(addr, dict):
                    loc_parts = [
                        addr.get("addressLocality"),
                        addr.get("addressRegion"),
                        addr.get("addressCountry"),
                    ]
                    location = ", ".join([p for p in loc_parts if p])
                elif isinstance(addr, str):
                    location = addr
            elif isinstance(job_loc, list) and job_loc:
                location = str(job_loc[0])
            elif isinstance(job_loc, str):
                location = job_loc

            # Recruiter / Hiring Org metadata
            recruiter_info = {}
            if isinstance(hiring_org, dict):
                recruiter_info["department"] = hiring_org.get("department")
                recruiter_info["url"] = hiring_org.get("url")
            if "author" in json_ld or "creator" in json_ld:
                author_val = json_ld.get("author") or json_ld.get("creator")
                recruiter_info["recruiter_name"] = author_val.get("name") if isinstance(author_val, dict) else str(author_val)
            if "email" in json_ld:
                recruiter_info["recruiter_email"] = json_ld.get("email")

            # Description
            raw_desc = json_ld.get("description", "")
            if "<" in raw_desc and ">" in raw_desc:
                raw_desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator="\n", strip=True)

            raw_payload = dict(json_ld)
            if recruiter_info:
                raw_payload["recruiter_metadata"] = recruiter_info

            return JobPosting(
                id=job_id,
                company=company,
                title=title,
                url=url,
                portal_type=portal_type,
                source="adhoc_ingestor",
                status=JobStatus.DISCOVERED,
                location=location,
                description=raw_desc or clean_text,
                raw_data=raw_payload,
            )

        # 2. DOM / Meta Fallback
        soup = BeautifulSoup(html_content, "html.parser")

        # Title
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
        elif soup.h1:
            title = soup.h1.get_text().strip()
        elif soup.title:
            title = soup.title.get_text().strip().split("|")[0].split("-")[0].strip()
        if not title:
            title = "Software Engineer"

        # Company
        company = ""
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            company = og_site["content"].strip()
        if not company:
            company = self._derive_company_name_from_url(url)

        # Location
        location = None
        loc_el = soup.find(class_=re.compile(r"(location|workplace|job-location)", re.I))
        if loc_el:
            location = loc_el.get_text(strip=True)

        return JobPosting(
            id=job_id,
            company=company,
            title=title,
            url=url,
            portal_type=portal_type,
            source="adhoc_ingestor",
            status=JobStatus.DISCOVERED,
            location=location,
            description=clean_text,
        )

    def from_url(self, url: str, html_content: Optional[str] = None) -> JobPosting:
        """Ingest job posting synchronously."""
        if html_content is None:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html_content = resp.text

        return self._parse_job_from_html(html_content, url)

    async def afrom_url(self, url: str, html_content: Optional[str] = None) -> JobPosting:
        """Ingest job posting asynchronously."""
        if html_content is None:
            async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html_content = resp.text

        return self._parse_job_from_html(html_content, url)
