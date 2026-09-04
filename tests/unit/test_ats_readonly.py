# tests/unit/test_ats_readonly.py
import json
from unittest.mock import MagicMock

import pytest

from src.core.events import EventType, reset_event_bus
from src.core.events.event_bus import get_event_bus
from src.integrations.ats_readonly import fetch_job_details, enrich_and_publish


def _client_with(payload_by_url: dict):
    """httpx.Client stub: .get(url) -> response with .status_code/.json()."""
    client = MagicMock()

    def get(url, **kw):
        resp = MagicMock()
        for frag, body in payload_by_url.items():
            if frag in str(url):
                resp.status_code = 200
                resp.json.return_value = body
                return resp
        resp.status_code = 404
        resp.json.return_value = {}
        return resp

    client.get.side_effect = get
    return client


def test_greenhouse_active():
    c = _client_with({"/boards/acme/jobs/123": {"id": 123, "title": "SRE",
                   "updated_at": "2026-08-01T00:00:00Z", "location": {"name": "Remote"}}})
    d = fetch_job_details("https://boards.greenhouse.io/acme/jobs/123", client=c)
    assert d["portal_type"] == "greenhouse" and d["active"] is True
    assert d["title"] == "SRE" and d["job_id"] == "123"


def test_greenhouse_gone_is_inactive():
    c = _client_with({})  # everything 404s
    d = fetch_job_details("https://boards.greenhouse.io/acme/jobs/999", client=c)
    assert d["active"] is False


def test_lever_and_ashby_and_smartrecruiters():
    c = _client_with({
        # lever single-posting endpoint is /v0/postings/{posting_id} (no token)
        "/postings/p-1": {"id": "p-1", "text": "BE",
            "createdAt": 1753000000000, "categories": {"location": "NYC"}},
        "api.ashbyhq.com/posting-api/job-board/acme":
            {"jobs": [{"id": "a-1", "title": "ML Eng",
                       "jobUrl": "https://jobs.ashbyhq.com/acme/a-1",
                       "publishedAt": "2026-07-20T00:00:00.000Z"}]},
        # smartrecruiters real-world posting ids are hex uuid-like
        "companies/Acme/postings/1234567890abcdef12345678":
            {"id": "1234567890abcdef12345678", "name": "Data Eng", "active": True,
             "releasedDate": "2026-07-01T10:00:00Z"},
    })
    assert fetch_job_details("https://jobs.lever.co/acme/p-1", client=c)["active"] is True
    a = fetch_job_details("https://jobs.ashbyhq.com/acme/a-1", client=c)
    assert a["title"] == "ML Eng" and a["active"] is True
    s = fetch_job_details("https://jobs.smartrecruiters.com/Acme/1234567890abcdef12345678", client=c)
    assert s["active"] is True and s["posted_at"].startswith("2026-07-01")


def test_unsupported_portal_returns_none():
    assert fetch_job_details("https://example.com/jobs/1", client=MagicMock()) is None


def test_enrich_publishes_event():
    reset_event_bus()
    bus = get_event_bus()
    seen = []
    bus.subscribe(EventType.JOB_ENRICHED, seen.append)
    c = _client_with({"/boards/acme/jobs/5": {"id": 5, "title": "T"}})
    d = enrich_and_publish("https://boards.greenhouse.io/acme/jobs/5", client=c)
    assert d is not None and len(seen) == 1
    assert seen[0].subject_id.endswith("/jobs/5")
