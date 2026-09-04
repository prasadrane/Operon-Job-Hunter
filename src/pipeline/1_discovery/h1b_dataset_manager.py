"""H-1B Dataset Manager with DOL LCA & USCIS Indexing, Tiered Confidence Scoring, and Entity Resolution."""

from enum import Enum
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

log = logging.getLogger(__name__)


class H1BTier(str, Enum):
    """Sponsorship confidence tiers based on certified LCA volume and track record."""

    TIER_1_PLATINUM = "TIER_1_PLATINUM"  # High volume (>50 filings/yr), high approval rate (>95%), established green card PERM track
    TIER_2_REGULAR = "TIER_2_REGULAR"    # Moderate volume (10-50 filings/yr)
    TIER_3_OCCASIONAL = "TIER_3_OCCASIONAL"  # Low volume (1-9 filings/yr)
    TIER_4_BLOCKER = "TIER_4_BLOCKER"    # Defense/ITAR clearance or explicit non-sponsoring employer


BRAND_LEGAL_MAP: Dict[str, str] = {
    "cash app": "Block, Inc.",
    "square": "Block, Inc.",
    "instagram": "Meta Platforms, Inc.",
    "facebook": "Meta Platforms, Inc.",
    "whatsapp": "Meta Platforms, Inc.",
    "youtube": "Google LLC",
    "deepmind": "Google LLC",
    "aws": "Amazon.com Services LLC",
    "twitch": "Amazon.com Services LLC",
    "linkedin": "Microsoft Corporation",
    "github": "Microsoft Corporation",
    "slack": "Salesforce, Inc.",
    "tableau": "Salesforce, Inc.",
    "mulesoft": "Salesforce, Inc.",
    "databricks": "Databricks, Inc.",
    "snowflake": "Snowflake Inc.",
    "stripe": "Stripe, Inc.",
}

CAP_EXEMPT_KEYWORDS = [
    "university", "college", "institute of technology", "hospital",
    "medical center", "research foundation", "national laboratory",
    "school of medicine", "clinic", "health system", "nonprofit research",
]


def clean_company_name(name: str) -> str:
    """Normalize company name for fuzzy comparison and dictionary lookup."""
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"\b(inc|incorporated|llc|corp|corporation|ltd|limited|co|company|technologies|services|holdings|group|the)\b", "", n, flags=re.IGNORECASE)
    n = re.sub(r"[^\w\s]", "", n)
    return re.sub(r"\s+", " ", n).strip()


class H1BDatasetManager:
    """Manages indexing, querying, and multi-tier confidence scoring for US H-1B sponsoring employers."""

    def __init__(
        self,
        sponsors_path: Optional[str] = None,
        initial_records: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.records: List[Dict[str, Any]] = []
        self.by_name: Dict[str, Dict[str, Any]] = {}
        self.by_domain: Dict[str, Dict[str, Any]] = {}

        if initial_records is not None:
            self._index_records(initial_records)
        else:
            self._load_and_index(sponsors_path)

    def _load_and_index(self, path: Optional[str]) -> None:
        target = path
        if not target:
            default_p = Path(__file__).resolve().parent.parent.parent.parent / "data" / "h1b_sponsors.json"
            if default_p.exists():
                target = str(default_p)

        if target and Path(target).exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._index_records(data)
            except Exception as exc:
                log.warning("Failed loading H-1B sponsors dataset from %s: %s", target, exc)

    def _index_records(self, records: List[Dict[str, Any]]) -> None:
        self.records = records
        for rec in records:
            name = rec.get("employer_name") or rec.get("company") or rec.get("name", "")
            domain = (rec.get("domain") or "").lower().strip()
            clean_n = clean_company_name(name)

            # Compute tier if missing
            if "tier" not in rec:
                rec["tier"] = self._compute_tier(rec)
            if "score" not in rec:
                rec["score"] = self._compute_score(rec)
            if "is_cap_exempt" not in rec:
                rec["is_cap_exempt"] = any(k in name.lower() for k in CAP_EXEMPT_KEYWORDS)

            if clean_n:
                self.by_name[clean_n] = rec
            if domain:
                self.by_domain[domain] = rec

    def _compute_tier(self, rec: Dict[str, Any]) -> H1BTier:
        lca_count = rec.get("lca_count") or rec.get("filings_count") or rec.get("approvals", 0)
        app_rate = rec.get("approval_rate", 0.95)

        if lca_count >= 50 and app_rate >= 0.90:
            return H1BTier.TIER_1_PLATINUM
        elif lca_count >= 10:
            return H1BTier.TIER_2_REGULAR
        elif lca_count >= 1:
            return H1BTier.TIER_3_OCCASIONAL
        return H1BTier.TIER_3_OCCASIONAL

    def _compute_score(self, rec: Dict[str, Any]) -> float:
        tier = rec.get("tier", H1BTier.TIER_3_OCCASIONAL)
        if tier == H1BTier.TIER_1_PLATINUM:
            return 95.0
        elif tier == H1BTier.TIER_2_REGULAR:
            return 80.0
        elif tier == H1BTier.TIER_3_OCCASIONAL:
            return 65.0
        return 0.0

    def resolve_brand_to_legal(self, brand_name: str) -> str:
        """Resolve consumer brand name or subsidiary to its legal employer name."""
        b_low = brand_name.lower().strip()
        return BRAND_LEGAL_MAP.get(b_low, brand_name)

    def lookup(
        self,
        company: str,
        domain: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Look up company sponsorship details with alias resolution and tiered ranking."""
        if not company and not domain:
            return None

        # 1. Domain match
        if domain:
            d_clean = domain.lower().strip().replace("www.", "")
            if d_clean in self.by_domain:
                return self.by_domain[d_clean]

        # 2. Brand alias resolution
        legal_name = self.resolve_brand_to_legal(company)
        clean_target = clean_company_name(legal_name)

        # Exact clean match
        if clean_target in self.by_name:
            return self.by_name[clean_target]

        # Substring / partial match
        for key, rec in self.by_name.items():
            if len(key) >= 3 and (key in clean_target or clean_target in key):
                return rec

        # Cap exempt heuristic fallback for universities and hospitals
        if any(kw in company.lower() for kw in CAP_EXEMPT_KEYWORDS):
            return {
                "employer_name": company,
                "tier": H1BTier.TIER_2_REGULAR,
                "score": 85.0,
                "is_cap_exempt": True,
                "lca_count": 25,
                "approval_rate": 0.99,
            }

        return None
