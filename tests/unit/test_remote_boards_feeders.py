# tests/unit/test_remote_boards_feeders.py
import importlib
from unittest.mock import MagicMock

# `1_discovery` is not a valid dotted-import identifier; sibling tests use importlib.
_rb_mod = importlib.import_module("src.pipeline.1_discovery.remote_boards")
AdzunaCrawler = _rb_mod.AdzunaCrawler
RemotiveCrawler = _rb_mod.RemotiveCrawler


def _resp(payload):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = payload
    return r


def test_remotive_maps_to_jobpostings():
    c = RemotiveCrawler(limit=2)
    client = MagicMock()
    client.get.return_value = _resp({"jobs": [
        {"id": 11, "url": "https://x/1", "title": "Backend Engineer",
         "company_name": "Acme", "location": "Remote",
         "publication_date": "2026-08-01T10:00:00", "description": "<p>hi</p>"},
    ]})
    jobs = c.fetch_jobs_with_client(client)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "remotive_11" and j.source == "remotive"
    assert j.company == "Acme" and j.portal_type == "remote"
    assert j.posted_at is not None and j.posted_at.tzinfo is not None


def test_adzuna_requires_credentials(monkeypatch):
    monkeypatch.setattr("src.pipeline.1_discovery.remote_boards.get_settings",
                        lambda: MagicMock(adzuna_app_id="", adzuna_app_key=""))
    c = AdzunaCrawler()
    assert c.fetch_jobs_with_client(MagicMock()) == []  # no call made


def test_adzuna_maps_and_dedups_fields():
    creds = MagicMock(adzuna_app_id="k", adzuna_app_key="s")
    rb = _rb_mod
    orig = rb.get_settings
    rb.get_settings = lambda: creds
    try:
        c = AdzunaCrawler(limit=10)
        client = MagicMock()
        client.get.return_value = _resp({"results": [
            {"id": "abc", "title": "SWE", "url": "https://y/2",
             "company": {"display_name": "BigCo"},
             "location": {"display_name": "Remote USA"},
             "created": "2026-08-02T00:00:00Z", "description": "d"},
        ]})
        jobs = c.fetch_jobs_with_client(client)
    finally:
        rb.get_settings = orig
    assert len(jobs) == 1 and jobs[0].id == "adzuna_abc"
    assert jobs[0].company == "BigCo"
    client.get.assert_called_once()
