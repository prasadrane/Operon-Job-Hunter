# src/integrations/ats_readonly.py
"""Read-only public ATS board API enrichment (P5b).

Scope discipline: these endpoints are ALL read-only job-board feeds.
No public ATS API allows submitting an application; submission stays
in src/pipeline/4_submission (browser tiers). This module exists for
job-detail truth checks: is the posting still live? when updated?
"""
import importlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from src.core.events import Event, EventType, get_event_bus

logger = logging.getLogger("careergraph.integrations.ats")

_pr = importlib.import_module("src.pipeline.1_discovery.portal_registry")
classify_portal_from_url = _pr.classify_portal_from_url
extract_board_token = _pr.extract_board_token

_TIMEOUT = 15.0


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gh_lever_job_id(url: str) -> Optional[str]:
    import re
    m = re.search(r"/jobs/(\d+)", url) or re.search(r"/job/([\w-]+)", url)
    return m.group(1) if m else None


def _greenhouse(url: str, client: httpx.Client) -> Optional[Dict[str, Any]]:
    token = extract_board_token(url)
    job_id = _gh_lever_job_id(url)
    if not (token and job_id and job_id.isdigit()):
        return None
    r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}")
    if r.status_code == 404:
        return {"portal_type": "greenhouse", "job_id": job_id, "active": False,
                "title": None, "posted_at": None, "fetched_at": _utc_iso()}
    r.raise_for_status()
    j = r.json()
    return {"portal_type": "greenhouse", "job_id": str(j.get("id") or job_id),
            "active": True, "title": j.get("title"),
            "posted_at": j.get("updated_at"), "fetched_at": _utc_iso()}


def _lever(url: str, client: httpx.Client) -> Optional[Dict[str, Any]]:
    token = extract_board_token(url)
    import re
    m = re.search(r"lever\.co/[^/]+/([\w-]+)", url)
    posting_id = m.group(1) if m else None
    if not (token and posting_id):
        return None
    r = client.get(f"https://api.lever.co/v0/postings/{posting_id}")
    if r.status_code == 404:
        return {"portal_type": "lever", "job_id": posting_id, "active": False,
                "title": None, "posted_at": None, "fetched_at": _utc_iso()}
    r.raise_for_status()
    j = r.json()
    created = j.get("createdAt")
    posted = (datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
              if isinstance(created, (int, float)) else None)
    return {"portal_type": "lever", "job_id": j.get("id") or posting_id,
            "active": True, "title": j.get("text"), "posted_at": posted,
            "fetched_at": _utc_iso()}


def _ashby(url: str, client: httpx.Client) -> Optional[Dict[str, Any]]:
    token = extract_board_token(url)
    job_id = url.rstrip("/").split("/")[-1]
    if not (token and job_id):
        return None
    r = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    r.raise_for_status()
    for job in r.json().get("jobs", []):
        if str(job.get("id")) == job_id or job.get("jobUrl", "").rstrip("/").endswith(f"/{job_id}"):
            return {"portal_type": "ashby", "job_id": str(job.get("id")),
                    "active": not job.get("isDeleted", False), "title": job.get("title"),
                    "posted_at": job.get("publishedAt"), "fetched_at": _utc_iso()}
    return {"portal_type": "ashby", "job_id": job_id, "active": False,
            "title": None, "posted_at": None, "fetched_at": _utc_iso()}


def _smartrecruiters(url: str, client: httpx.Client) -> Optional[Dict[str, Any]]:
    import re
    m = re.search(r"jobs\.smartrecruiters\.com/([^/]+)/([0-9a-fA-F-]{20,})", url)
    if not m:
        return None
    company, posting_id = m.group(1), m.group(2)
    r = client.get(f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting_id}")
    if r.status_code == 404:
        return {"portal_type": "smartrecruiters", "job_id": posting_id,
                "active": False, "title": None, "posted_at": None, "fetched_at": _utc_iso()}
    r.raise_for_status()
    j = r.json()
    return {"portal_type": "smartrecruiters", "job_id": j.get("id") or posting_id,
            "active": bool(j.get("active", True)), "title": j.get("name"),
            "posted_at": j.get("releasedDate"), "fetched_at": _utc_iso()}


_DISPATCH = {"greenhouse": _greenhouse, "lever": _lever,
             "ashby": _ashby, "smartrecruiters": _smartrecruiters}


def fetch_job_details(url: str, client: Optional[httpx.Client] = None) -> Optional[Dict[str, Any]]:
    portal = classify_portal_from_url(url)
    fn = _DISPATCH.get(portal)
    if fn is None:
        logger.debug("ats_readonly: unsupported portal %s for %s", portal, url)
        return None
    owns_client = client is None
    http = client or httpx.Client(timeout=_TIMEOUT)
    try:
        return fn(url, http)
    except Exception as exc:  # noqa: BLE001 — enrichment is best-effort by design
        logger.warning("ats_readonly failed for %s: %s", url, exc)
        return None
    finally:
        if owns_client:
            http.close()


def enrich_and_publish(url: str, client: Optional[httpx.Client] = None) -> Optional[Dict[str, Any]]:
    details = fetch_job_details(url, client=client)
    if details is not None:
        get_event_bus().publish(Event(
            event_type=EventType.JOB_ENRICHED, source="ats_readonly",
            subject_id=url, payload=details))
    return details
