"""Ghost Job & Posting Legitimacy Detector for CareerGraph AI."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from src.core.models import JobPosting


class GhostJobReport(BaseModel):
    """Report detailing posting legitimacy, scam markers, and ghost job signals."""

    legitimacy_score: float = 100.0
    is_ghost_job: bool = False
    is_scam: bool = False
    reasons: List[str] = Field(default_factory=list)
    flags: Dict[str, Any] = Field(default_factory=dict)


class GhostJobDetector:
    """Evaluates job postings for scam indicators, phantom listings, and ghost-job signals."""

    # Public / generic email domains used in scams
    SCAM_EMAIL_PATTERN = re.compile(
        r"(?:send\s+(?:your\s+)?(?:resume|cv)|contact|apply|email)\s+(?:to\s+)?[a-zA-Z0-9_.+-]+@(gmail|yahoo|hotmail|outlook|aol|protonmail)\.com",
        re.IGNORECASE,
    )

    # Messaging app interview scams
    MESSAGING_SCAM_PATTERN = re.compile(
        r"\b(?:interview\s+(?:via|on|through)|message\s+us\s+on|contact\s+via)\s+(?:telegram|whatsapp|signal|google\s+hangouts|skype|wire)\b|"
        r"@(telegram|whatsapp)\b|\b(?:telegram|whatsapp)\s+@?[a-zA-Z0-9_]{3,}\b",
        re.IGNORECASE,
    )

    # Financial / advance-fee scam markers
    FINANCIAL_SCAM_PATTERN = re.compile(
        r"\b(?:check\s+deposit|equipment\s+check|upfront\s+(?:fee|payment)|pay\s+for\s+(?:background|training|equipment)|"
        r"wire\s+transfer|crypto|bitcoin|send\s+money|cashier'?s\s+check)\b",
        re.IGNORECASE,
    )

    # Placeholder and broken template markers
    PLACEHOLDER_PATTERN = re.compile(
        r"\b(?:lorem\s+ipsum|\[company\s+name\]|\[insert\s+title\]|\bxxx\b|sample\s+job\s+description)\b",
        re.IGNORECASE,
    )

    # Evergreen / phantom listing markers
    EVERGREEN_PATTERN = re.compile(
        r"\b(?:evergreen\s+requisition|talent\s+pool\s+(?:posting|application)|"
        r"always\s+(?:accepting|hiring\s+for\s+future)|pipeline\s+requisition|"
        r"general\s+consideration\s+only)\b",
        re.IGNORECASE,
    )

    def detect(
        self,
        job: Union[JobPosting, Dict[str, Any]],
        days_open: Optional[int] = None,
        repost_count: int = 0,
    ) -> GhostJobReport:
        """Analyze job description and metadata for scam, ghost-job, or staleness flags."""
        if isinstance(job, JobPosting):
            desc = job.description or ""
            company = job.company or ""
            title = job.title or ""
            raw = job.raw_data or {}
        else:
            desc = job.get("description", "") or ""
            company = job.get("company", "") or ""
            title = job.get("title", "") or ""
            raw = job.get("raw_data", {}) or {}

        # Resolve days open from arguments or raw data
        if days_open is None:
            days_open = raw.get("days_open", 0)

        # Resolve repost count
        if repost_count == 0:
            repost_count = raw.get("repost_count", 0)

        score = 100.0
        reasons: List[str] = []
        flags: Dict[str, Any] = {}
        is_scam = False
        is_ghost_job = False

        full_text = f"{title}\n{company}\n{desc}"

        # 1. Scam check: Public email domains for resume submission
        if self.SCAM_EMAIL_PATTERN.search(full_text) or "@gmail.com" in desc.lower() or "@yahoo.com" in desc.lower():
            is_scam = True
            is_ghost_job = True
            score -= 45.0
            reasons.append("Scam marker: Job asks to send resume to a public generic email domain (e.g., Gmail/Yahoo).")
            flags["public_email_contact"] = True

        # 2. Scam check: Messaging app interview
        if self.MESSAGING_SCAM_PATTERN.search(full_text):
            is_scam = True
            is_ghost_job = True
            score -= 40.0
            reasons.append("Scam marker: Job requests interview or contact via Telegram/WhatsApp/messaging app.")
            flags["messaging_app_interview"] = True

        # 3. Scam check: Advance fee / financial checks
        if self.FINANCIAL_SCAM_PATTERN.search(full_text):
            is_scam = True
            is_ghost_job = True
            score -= 50.0
            reasons.append("Scam marker: Mentions upfront check deposit, equipment fee, or wire transfer.")
            flags["financial_advance_fee"] = True

        # 4. Template placeholder check
        if self.PLACEHOLDER_PATTERN.search(full_text):
            score -= 30.0
            reasons.append("Posting contains placeholder or template boilerplate text.")
            flags["placeholder_text"] = True

        # 5. Stale / Ghost job check: Open > 180 days (> 6 months)
        if days_open > 180:
            is_ghost_job = True
            score -= 35.0
            reasons.append(f"Ghost job indicator: Role has been open/reposted for >180 days ({days_open} days).")
            flags["days_open_exceeded"] = days_open
        elif days_open > 90:
            score -= 15.0
            reasons.append(f"Stale posting indicator: Role open for >90 days ({days_open} days).")
            flags["stale_posting"] = days_open

        # 6. High repost frequency
        if repost_count >= 5:
            is_ghost_job = True
            score -= 20.0
            reasons.append(f"Ghost job indicator: Role has been reposted {repost_count} times without being filled.")
            flags["repost_count_exceeded"] = repost_count

        # 7. Evergreen / talent pool listing
        if self.EVERGREEN_PATTERN.search(full_text):
            score -= 20.0
            reasons.append("Posting is an evergreen pipeline / talent pool requisition without active immediate opening.")
            flags["evergreen_requisition"] = True

        # 8. Empty or minimal description check
        if len(desc.strip()) < 40:
            score -= 25.0
            reasons.append("Job description is missing or excessively brief (< 40 characters).")
            flags["minimal_description"] = True

        # Bound score between 0.0 and 100.0
        final_score = max(0.0, min(100.0, score))

        if final_score < 60.0:
            is_ghost_job = True

        return GhostJobReport(
            legitimacy_score=final_score,
            is_ghost_job=is_ghost_job,
            is_scam=is_scam,
            reasons=reasons,
            flags=flags,
        )
