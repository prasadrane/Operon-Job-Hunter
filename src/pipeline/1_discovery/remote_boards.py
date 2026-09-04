"""API-backed remote job boards (P5b). Both are public JSON APIs — no
Cloudflare gauntlet, unlike Indeed/Glassdoor HTML which jobspy already
pruned (see jobspy_scraper.py:37). Follows JobicyCrawler conventions in
aggregators.py: sync fetch + async_fetch(client), [] on failure."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from src.core.config import get_settings
from src.core.models import JobPosting, JobStatus

log = logging.getLogger("careergraph.discovery.remote_boards")

_TIMEOUT = 20.0


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class RemotiveCrawler:
    """https://remotive.com/api/remote-jobs — open JSON, no auth."""

    def __init__(self, limit: int = 200) -> None:
        self.limit = limit

    def fetch_jobs_with_client(self, client: httpx.Client) -> List[JobPosting]:
        try:
            r = client.get("https://remotive.com/api/remote-jobs")
            r.raise_for_status()
            raw = r.json().get("jobs", [])[: self.limit]
        except Exception as exc:  # noqa: BLE001
            log.warning("Remotive fetch failed: %s", exc)
            return []
        return [self._to_posting(j) for j in raw if self._ok(j)]

    def fetch_jobs(self) -> List[JobPosting]:
        with httpx.Client(timeout=_TIMEOUT) as client:
            return self.fetch_jobs_with_client(client)

    async def async_fetch_jobs(self, client: Optional[httpx.AsyncClient] = None) -> List[JobPosting]:
        owns = client is None
        aclient = client or httpx.AsyncClient(timeout=_TIMEOUT)
        try:
            r = await aclient.get("https://remotive.com/api/remote-jobs")
            r.raise_for_status()
            raw = r.json().get("jobs", [])[: self.limit]
        except Exception as exc:  # noqa: BLE001
            log.warning("Remotive async fetch failed: %s", exc)
            return []
        finally:
            if owns:
                await aclient.aclose()
        return [self._to_posting(j) for j in raw if self._ok(j)]

    @staticmethod
    def _ok(j: dict) -> bool:
        return bool(j.get("id") and j.get("url") and j.get("title"))

    @staticmethod
    def _to_posting(j: dict) -> JobPosting:
        return JobPosting(
            id=f"remotive_{j['id']}", company=str(j.get("company_name") or "Unknown"),
            title=str(j["title"]), url=str(j["url"]), portal_type="remote",
            source="remotive", status=JobStatus.DISCOVERED,
            location=j.get("location"), description=j.get("description"),
            posted_at=_parse_dt(j.get("publication_date")),
        )


class AdzunaCrawler:
    """https://developer.adzuna.com — free developer key required."""

    def __init__(self, limit: int = 50, country: str = "us") -> None:
        self.limit = limit
        self.country = country

    def fetch_jobs_with_client(self, client: httpx.Client) -> List[JobPosting]:
        cfg = get_settings()
        app_id = cfg.adzuna_app_id
        app_key = cfg.adzuna_app_key
        if not (app_id and app_key):
            log.warning("Adzuna skipped: ADZUNA_APP_ID/ADZUNA_APP_KEY unset")
            return []
        params = {"app_id": app_id, "app_key": app_key,
                  "results_per_page": self.limit, "what": "software engineer"}
        try:
            r = client.get(f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/1",
                           params=params)
            r.raise_for_status()
            raw = r.json().get("results", [])
        except Exception as exc:  # noqa: BLE001
            log.warning("Adzuna fetch failed: %s", exc)
            return []
        return [self._to_posting(j) for j in raw if j.get("id") and j.get("url")]

    def fetch_jobs(self) -> List[JobPosting]:
        with httpx.Client(timeout=_TIMEOUT) as client:
            return self.fetch_jobs_with_client(client)

    @staticmethod
    def _to_posting(j: dict) -> JobPosting:
        return JobPosting(
            id=f"adzuna_{j['id']}",
            company=str((j.get("company") or {}).get("display_name") or "Unknown"),
            title=str(j.get("title") or ""), url=str(j["url"]),
            portal_type="remote", source="adzuna", status=JobStatus.DISCOVERED,
            location=(j.get("location") or {}).get("display_name"),
            description=j.get("description"),
            posted_at=_parse_dt(j.get("created")),
        )
