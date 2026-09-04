"""Preflight Screener: Live form inspection for knockout criteria, illegal status screening, and prohibited questions."""

from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PreflightStatus(str, Enum):
    PASSED = "passed"
    KNOCKOUT_DISQUALIFIED = "knockout_disqualified"
    BLACKLISTED = "blacklisted"
    DUPLICATE_APPLICATION = "duplicate_application"


@dataclass
class PreflightResult:
    status: PreflightStatus
    reason: str = ""
    has_status_screening_warning: bool = False
    status_screening_details: str = ""
    has_prohibited_content_warning: bool = False
    prohibited_content_details: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class PreflightScreener:
    """Live-page preflight gate inspecting forms for knockouts, legality, and blacklist status."""

    # Disqualification patterns for visa sponsorship
    NO_SPONSORSHIP_PATTERNS = [
        r"unable to (?:provide|sponsor|offer) (?:visa|employment|h-?1b)?\s*sponsorship",
        r"cannot (?:provide|sponsor|offer) (?:visa|employment|h-?1b)?\s*sponsorship",
        r"no (?:visa|employment|h-?1b)?\s*sponsorship (?:is )?(?:provided|available|offered)",
        r"not (?:offering|providing|sponsoring) (?:visa|employment|h-?1b)?\s*sponsorship",
        r"sponsorship (?:is )?not (?:available|supported|offered)",
        r"must not require (?:visa|employment|h-?1b)?\s*sponsorship",
    ]

    # Specific immigration status demands (vs lawful work authorization)
    STATUS_SCREENING_PATTERNS = [
        r"u\.?s\.?\s*citizen(?:ship)?\s*or\s*(?:permanent resident|green card)",
        r"citizen(?:ship)?\s*or\s*permanent resident",
        r"are you a (?:u\.?s\.?\s*)?citizen",
        r"authorized to work (?:in [a-z\s]+ )?on a permanent basis",
    ]

    # Prohibited salary history inquiries
    SALARY_HISTORY_PATTERNS = [
        r"(?:previous|past|current|prior|last)\s*(?:salary|compensation|base pay|pay rate|earnings)",
        r"salary\s*(?:or compensation\s*)?at your (?:last|previous|current) job",
    ]

    # US jurisdictions prohibiting salary history
    SALARY_HISTORY_BANNED_JURISDICTIONS = {
        "ca", "california", "ny", "new york", "il", "illinois", "ma", "massachusetts",
        "wa", "washington", "co", "colorado", "nj", "new jersey", "or", "oregon",
    }

    def __init__(self, blacklist_path: str = "./data/blacklist.json") -> None:
        self.blacklist_path = blacklist_path
        self._blacklist = self._load_blacklist()

    def _load_blacklist(self) -> Set[str]:
        if os.path.exists(self.blacklist_path):
            try:
                with open(self.blacklist_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return {c.strip().lower() for c in data if isinstance(c, str)}
            except Exception as e:
                logger.debug("Failed to load blacklist from %s: %s", self.blacklist_path, e)
        return set()

    def screen_page(
        self,
        page_or_frame: Any,
        company: str,
        profile: Dict[str, Any],
    ) -> PreflightResult:
        """Run preflight checks across blacklist, knockouts, status screening, and prohibited content."""
        clean_company = company.strip().lower()

        # 1. Blacklist check
        if clean_company in self._blacklist:
            return PreflightResult(
                status=PreflightStatus.BLACKLISTED,
                reason=f"Company '{company}' is on the candidate blacklist.",
            )

        page_text = ""
        try:
            if hasattr(page_or_frame, "content") and callable(page_or_frame.content):
                res = page_or_frame.content()
                if isinstance(res, str):
                    page_text = res
            elif hasattr(page_or_frame, "inner_text") and callable(page_or_frame.inner_text):
                res = page_or_frame.inner_text("body")
                if isinstance(res, str):
                    page_text = res
        except Exception:
            page_text = ""

        page_lower = page_text.lower() if isinstance(page_text, str) else ""
        requires_sponsorship = profile.get("requires_sponsorship", False)
        candidate_loc = str(profile.get("location", "")).lower()

        # 2. Knockout Check: Visa Sponsorship
        if requires_sponsorship:
            for pattern in self.NO_SPONSORSHIP_PATTERNS:
                if re.search(pattern, page_lower, re.IGNORECASE):
                    return PreflightResult(
                        status=PreflightStatus.KNOCKOUT_DISQUALIFIED,
                        reason="Form explicitly states visa sponsorship is not provided or supported.",
                    )

        # 3. Immigration Status Screening Warning (Warn-only)
        has_status_warning = False
        status_warning_details = ""
        for pattern in self.STATUS_SCREENING_PATTERNS:
            match = re.search(pattern, page_lower, re.IGNORECASE)
            if match:
                has_status_warning = True
                status_warning_details = (
                    f"Form question matches '{match.group(0)}', which screens for specific immigration status "
                    "rather than legal work authorization."
                )
                break

        # 4. Prohibited Content Check: Salary History (Warn-only)
        has_prohibited_warning = False
        prohibited_details = ""
        loc_tokens = re.findall(r"\b[a-z]{2,}\b", candidate_loc)
        is_banned_jurisdiction = any(tok in self.SALARY_HISTORY_BANNED_JURISDICTIONS for tok in loc_tokens)

        if is_banned_jurisdiction:
            for pattern in self.SALARY_HISTORY_PATTERNS:
                match = re.search(pattern, page_lower, re.IGNORECASE)
                if match:
                    has_prohibited_warning = True
                    prohibited_details = (
                        f"Form inquires about '{match.group(0)}', which is prohibited by salary history ban legislation "
                        f"in your jurisdiction ({profile.get('location')})."
                    )
                    break

        return PreflightResult(
            status=PreflightStatus.PASSED,
            reason="Preflight inspection passed all knockout rules.",
            has_status_screening_warning=has_status_warning,
            status_screening_details=status_warning_details,
            has_prohibited_content_warning=has_prohibited_warning,
            prohibited_content_details=prohibited_details,
        )
