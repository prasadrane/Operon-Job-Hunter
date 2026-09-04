"""Unified ATS portal detection, board token extraction, and URL canonicalization."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def classify_portal_from_url(url: str) -> str:
    """Detect underlying ATS portal type from job URL."""
    if not url:
        return "generic"
    low = url.lower()
    if "greenhouse.io" in low:
        return "greenhouse"
    elif "lever.co" in low:
        return "lever"
    elif "ashbyhq.com" in low:
        return "ashby"
    elif "myworkdayjobs.com" in low:
        return "workday"
    elif "smartrecruiters.com" in low:
        return "smartrecruiters"
    elif "amazon.jobs" in low:
        return "amazon"
    elif "careers.microsoft.com" in low:
        return "microsoft"
    elif "careers.google.com" in low:
        return "google"
    return "generic"


def extract_board_token(url: str) -> Optional[str]:
    """Extract ATS board_token from a career site URL."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    path_parts = [p for p in parsed.path.split("/") if p]

    if not host or not path_parts:
        return None

    # Greenhouse: boards.greenhouse.io/{token}[/jobs/...] or boards-api.greenhouse.io/v1/boards/{token}
    if "greenhouse.io" in host:
        if "boards-api" in host and len(path_parts) >= 3:
            for i, part in enumerate(path_parts):
                if part == "boards" and i + 1 < len(path_parts):
                    return path_parts[i + 1].lower()
        return path_parts[0].lower()

    # Lever: jobs.lever.co/{token}[/{job_id}]
    if "lever.co" in host:
        return path_parts[0].lower()

    # Ashby: jobs.ashbyhq.com/{token}[/{job_id}]
    if "ashbyhq.com" in host:
        return path_parts[0].lower()

    # SmartRecruiters: jobs.smartrecruiters.com/{token}/{posting_id}
    if "smartrecruiters.com" in host:
        return path_parts[0].lower()

    # Workday: {tenant}.wd{N}.myworkdayjobs.com/{board}/job/{path} or /en-US/{board}/job/{path}
    if "myworkdayjobs.com" in host:
        if path_parts[0].lower() in {"en-us", "en"} and len(path_parts) > 1:
            return path_parts[1].lower()
        if path_parts[0].lower() not in {"job", "jobs"}:
            return path_parts[0].lower()
        m2 = re.search(r"https?://([a-zA-Z0-9_-]+)\.(wd\d+\.)?myworkdayjobs\.com", url)
        if m2:
            return m2.group(1).lower()

    return None


def canonicalize_url(url: str) -> str:
    """Strip UTM parameters, session tokens, and tracking queries from job URLs."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        qs = parse_qs(parsed.query)
        # Strip tracking params
        tracking_keys = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gh_jid", "ref", "source"}
        filtered_qs = {k: v for k, v in qs.items() if k.lower() not in tracking_keys}
        new_query = urlencode(filtered_qs, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.params, new_query, ""))
    except Exception:
        return url.strip()
