"""Robust job posting datetime parser supporting ISO, epoch ms, RFC 2822, and relative strings."""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def parse_job_posted_date(raw_val: Any) -> Optional[datetime]:
    """Parse and normalize diverse ATS job posting timestamps to a UTC datetime object.

    Handles:
    - ISO-8601 strings (e.g., "2026-08-20T14:30:00Z", "2026-08-21T09:15:00-04:00")
    - UNIX timestamps (integer/float in seconds or milliseconds, e.g. Lever createdAt)
    - RFC 2822 dates (e.g., "Wed, 19 Aug 2026 12:00:00 GMT")
    - Relative English phrases (e.g. "Posted Today", "Posted Yesterday", "Posted 2 Days Ago",
      "Posted 30+ Days Ago", "3 hours ago", "Just posted")
    - Standard date strings (e.g. "2026-08-22", "2026-08-22 18:00:00")
    """
    if raw_val is None:
        return None

    # Handle already parsed datetime instances
    if isinstance(raw_val, datetime):
        if raw_val.tzinfo is None:
            return raw_val.replace(tzinfo=timezone.utc)
        return raw_val.astimezone(timezone.utc)

    # Handle numeric epoch timestamp (seconds or milliseconds)
    if isinstance(raw_val, (int, float)):
        try:
            val_f = float(raw_val)
            # If greater than 10^11, assume milliseconds
            if val_f > 1e11:
                val_f = val_f / 1000.0
            return datetime.fromtimestamp(val_f, tz=timezone.utc)
        except Exception:
            return None

    val_str = str(raw_val).strip()
    if not val_str or val_str.lower() in ("n/a", "none", "null", "unknown"):
        return None

    # Try numeric string (e.g. "1787400000000")
    if val_str.isdigit():
        try:
            val_f = float(val_str)
            if val_f > 1e11:
                val_f = val_f / 1000.0
            return datetime.fromtimestamp(val_f, tz=timezone.utc)
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    val_lower = val_str.lower()

    # Handle relative phrases
    if "just posted" in val_lower or "moments ago" in val_lower or "now" in val_lower:
        return now

    if "today" in val_lower:
        return now

    if "yesterday" in val_lower:
        return now - timedelta(days=1)

    # e.g., "Posted 30+ Days Ago", "30+ days ago"
    match_plus_days = re.search(r"(\d+)\+\s*days?\s*ago", val_lower)
    if match_plus_days:
        days = int(match_plus_days.group(1))
        return now - timedelta(days=days)

    # e.g., "Posted 2 Days Ago", "2 days ago", "posted 5d ago"
    match_days = re.search(r"(?:posted\s*)?(\d+)\s*(?:days?|d)\s*ago", val_lower)
    if match_days:
        days = int(match_days.group(1))
        return now - timedelta(days=days)

    # e.g., "3 hours ago", "posted 4h ago"
    match_hours = re.search(r"(?:posted\s*)?(\d+)\s*(?:hours?|hrs?|h)\s*ago", val_lower)
    if match_hours:
        hours = int(match_hours.group(1))
        return now - timedelta(hours=hours)

    # e.g., "45 minutes ago", "posted 15m ago"
    match_mins = re.search(r"(?:posted\s*)?(\d+)\s*(?:minutes?|mins?|m)\s*ago", val_lower)
    if match_mins:
        mins = int(match_mins.group(1))
        return now - timedelta(minutes=mins)

    # Try ISO-8601 parsing (datetime.fromisoformat handles "2026-08-20T14:30:00Z" in Python 3.11+)
    iso_candidate = val_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Try RFC 2822 (e.g. RSS feed dates: "Wed, 19 Aug 2026 12:00:00 GMT")
    try:
        dt = parsedate_to_datetime(val_str)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Try common explicit date formats
    date_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%Y %H:%M:%S",
        "%d-%m-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(val_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue

    logger.debug("Could not parse date string: %s", val_str)
    return None
