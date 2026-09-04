"""Lightweight RSS / Atom Feed Crawler for Sub-60s ATS Job Discovery using built-in ElementTree."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET
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
    "Accept": "application/rss+xml, application/atom+xml, text/xml, application/xml, */*",
}


class RSSFeedCrawler:
    """Consumes RSS and Atom feeds for instantaneous job opening updates with low bandwidth."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def fetch_feed(self, feed_url: str, company_name: str) -> List[JobPosting]:
        """Synchronously fetch and parse RSS/Atom feed."""
        return asyncio.run(self.async_fetch_feed(feed_url, company_name))

    async def async_fetch_feed(
        self,
        feed_url: str,
        company_name: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[JobPosting]:
        """Asynchronously fetch and parse RSS/Atom feed into JobPosting models."""
        jobs: List[JobPosting] = []
        try:
            local_client = client or httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout)
            try:
                resp = await local_client.get(feed_url)
                if resp.status_code != 200:
                    return []

                root = ET.fromstring(resp.text.strip())

                # Search RSS items (e.g. root/channel/item or .//item)
                rss_items = root.findall(".//item")
                if rss_items:
                    for item in rss_items:
                        title_el = item.find("title")
                        title = title_el.text.strip() if title_el is not None and title_el.text else "Software Engineer"

                        link_el = item.find("link")
                        url = link_el.text.strip() if link_el is not None and link_el.text else ""
                        if not url:
                            continue

                        guid_el = item.find("guid")
                        posting_id = guid_el.text.strip() if guid_el is not None and guid_el.text else str(hash(url))

                        desc_el = item.find("description")
                        raw_desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                        clean_desc = clean_html_description(raw_desc)

                        pubdate_el = item.find("pubDate")
                        posted_at = parse_job_posted_date(pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else None)

                        portal_type = classify_portal_from_url(url)

                        jobs.append(
                            JobPosting(
                                id=f"rss_{company_name.lower().replace(' ', '_')}_{posting_id}",
                                company=company_name,
                                title=title,
                                url=url,
                                portal_type=portal_type,
                                source="rss_feed",
                                status=JobStatus.DISCOVERED,
                                location="United States",
                                description=clean_desc,
                                posted_at=posted_at,
                            )
                        )
                else:
                    # Search Atom entries (e.g. .//{*}entry)
                    atom_entries = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//entry")
                    for entry in atom_entries:
                        title_el = entry.find("{http://www.w3.org/2005/Atom}title") or entry.find("title")
                        title = title_el.text.strip() if title_el is not None and title_el.text else "Software Engineer"

                        link_el = entry.find("{http://www.w3.org/2005/Atom}link") or entry.find("link")
                        url = ""
                        if link_el is not None:
                            url = link_el.get("href") or (link_el.text.strip() if link_el.text else "")
                        if not url:
                            continue

                        id_el = entry.find("{http://www.w3.org/2005/Atom}id") or entry.find("id")
                        posting_id = id_el.text.strip() if id_el is not None and id_el.text else str(hash(url))

                        summary_el = entry.find("{http://www.w3.org/2005/Atom}summary") or entry.find("summary") or entry.find("{http://www.w3.org/2005/Atom}content") or entry.find("content")
                        raw_desc = summary_el.text.strip() if summary_el is not None and summary_el.text else ""
                        clean_desc = clean_html_description(raw_desc)

                        updated_el = entry.find("{http://www.w3.org/2005/Atom}updated") or entry.find("updated") or entry.find("{http://www.w3.org/2005/Atom}published") or entry.find("published")
                        posted_at = parse_job_posted_date(updated_el.text.strip() if updated_el is not None and updated_el.text else None)

                        portal_type = classify_portal_from_url(url)

                        jobs.append(
                            JobPosting(
                                id=f"rss_{company_name.lower().replace(' ', '_')}_{posting_id}",
                                company=company_name,
                                title=title,
                                url=url,
                                portal_type=portal_type,
                                source="rss_feed",
                                status=JobStatus.DISCOVERED,
                                location="United States",
                                description=clean_desc,
                                posted_at=posted_at,
                            )
                        )
            finally:
                if client is None:
                    await local_client.aclose()
        except Exception as exc:
            log.warning("Failed parsing RSS feed from %s: %s", feed_url, exc)

        return jobs
