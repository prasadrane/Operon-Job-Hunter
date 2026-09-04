"""H-1B sponsorship checker and visa requirement analyzer."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .h1b_dataset_manager import H1BDatasetManager, H1BTier

log = logging.getLogger(__name__)

# Regular expressions for cleaning company names
LEGAL_SUFFIXES_RE = re.compile(
    r"\b(inc|incorporated|llc|corp|corporation|ltd|limited|co|company|technologies|technology|services|holdings|group|the)\b",
    re.IGNORECASE,
)
PUNCTUATION_RE = re.compile(r"[^\w\s]")

# Visa blocker phrases (explicit indication that employer will NOT sponsor)
BLOCKER_PATTERNS = [
    "must be authorized to work in the us without sponsorship",
    "must be authorized to work in the united states without sponsorship",
    "authorized to work in the us without sponsorship",
    "authorized to work in the united states without sponsorship",
    "without sponsorship now or in the future",
    "without need for sponsorship",
    "without requirement of sponsorship",
    "unable to provide visa sponsorship",
    "unable to provide sponsorship",
    "unable to sponsor",
    "cannot provide visa sponsorship",
    "cannot provide sponsorship",
    "cannot sponsor",
    "will not sponsor",
    "will not provide visa sponsorship",
    "will not provide sponsorship",
    "not offering visa sponsorship",
    "not offering sponsorship",
    "no visa sponsorship",
    "no sponsorship available",
    "no sponsorship",
    "not sponsor",
    "not provide sponsorship",
    "no h-1b",
    "no h1b",
    "u.s. citizen or green card",
    "us citizen or green card",
    "u.s. citizen or permanent resident",
    "us citizen or permanent resident",
    "u.s. citizenship required",
    "us citizenship required",
    "must be a u.s. citizen",
    "must be a us citizen",
    "must be us citizen",
    "security clearance required",
    "active security clearance",
    "top secret clearance",
    "ts/sci",
]

# Confirmed sponsorship phrases (explicit indication that employer DOES sponsor)
CONFIRMED_PATTERNS = [
    "visa sponsorship",
    "h-1b sponsorship",
    "h1b sponsorship",
    "h-1b visa",
    "h1b visa",
    "h-1b transfer",
    "h1b transfer",
    "will sponsor",
    "can sponsor",
    "offers sponsorship",
    "offer sponsorship",
    "provides sponsorship",
    "provide sponsorship",
    "sponsors h-1b",
    "sponsors h1b",
    "sponsors visa",
    "sponsor visa",
    "sponsorship is available",
    "sponsorship available",
    "sponsorship provided",
    "open to visa sponsorship",
    "eligible for visa sponsorship",
    "visa support provided",
    "visa support",
]


class H1BChecker:
    """Evaluates company-level H-1B sponsorship history and analyzes JD text for visa constraints."""

    def __init__(
        self,
        sponsors_path: Optional[str] = None,
        sponsors_data: Optional[List[Dict[str, Any]]] = None,
        dataset_manager: Optional[H1BDatasetManager] = None,
    ) -> None:
        self.sponsors: List[Dict[str, Any]] = []
        self.domain_map: Dict[str, Dict[str, Any]] = {}
        self.name_map: Dict[str, Dict[str, Any]] = {}
        self.dataset_manager = dataset_manager or H1BDatasetManager(sponsors_path=sponsors_path, initial_records=sponsors_data)

        if sponsors_data is not None:
            self._load_data(sponsors_data)
        elif sponsors_path is not None:
            self._load_file(Path(sponsors_path))
        else:
            default_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "h1b_sponsors.json"
            if default_path.exists():
                self._load_file(default_path)
            else:
                fallback_local = Path("data/h1b_sponsors.json")
                if fallback_local.exists():
                    self._load_file(fallback_local)

    def _load_data(self, data: List[Dict[str, Any]]) -> None:
        self.sponsors = data
        for item in data:
            domain = item.get("domain", "").lower().strip().replace("www.", "")
            if domain:
                self.domain_map[domain] = item
            name = item.get("name", "")
            if name:
                norm = self.normalize_name(name)
                self.name_map[norm] = item

    def _load_file(self, path: Path) -> None:
        if not path.exists():
            log.warning("H1B sponsors file not found at %s", path)
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    # Handle both list of dicts or list of strings
                    parsed_data = []
                    for item in data:
                        if isinstance(item, dict):
                            parsed_data.append(item)
                        elif isinstance(item, str):
                            parsed_data.append({"name": item, "domain": "", "confidence": "confirmed"})
                    self._load_data(parsed_data)
        except Exception as exc:
            log.error("Failed to load H1B sponsors from %s: %s", path, exc)

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize company name by stripping legal suffixes and punctuation."""
        if not name:
            return ""
        text = name.lower()
        text = PUNCTUATION_RE.sub(" ", text)
        text = LEGAL_SUFFIXES_RE.sub(" ", text)
        return " ".join(text.split()).strip()

    def get_sponsor_confidence(self, company: str, domain: Optional[str] = None) -> str:
        """Return sponsorship confidence level: 'confirmed', 'likely', or 'unknown'."""
        # 1. Match domain if provided
        if domain:
            cleaned_domain = domain.lower().strip().replace("http://", "").replace("https://", "").replace("www.", "").split("/")[0]
            if cleaned_domain in self.domain_map:
                conf = self.domain_map[cleaned_domain].get("confidence", "likely")
                return "confirmed" if conf in ("confirmed", "high") else "likely"

        if not company:
            return "unknown"

        # 2. Match exact normalized name
        norm_company = self.normalize_name(company)
        if norm_company in self.name_map:
            conf = self.name_map[norm_company].get("confidence", "likely")
            return "confirmed" if conf in ("confirmed", "high") else "likely"

        # 3. Substring / partial matching
        if len(norm_company) >= 4:
            for sponsor_norm, info in self.name_map.items():
                if len(sponsor_norm) >= 4:
                    if norm_company in sponsor_norm or sponsor_norm in norm_company:
                        conf = info.get("confidence", "likely")
                        return "confirmed" if conf in ("confirmed", "high") else "likely"

        return "unknown"

    def is_sponsor(self, company: str, domain: Optional[str] = None) -> bool:
        """Return True if company is a verified or likely H-1B sponsor."""
        confidence = self.get_sponsor_confidence(company, domain)
        return confidence in ("confirmed", "likely")

    def check_jd_sponsorship(self, jd_text: Optional[str]) -> str:
        """Analyze job description text for explicit visa sponsorship clauses.
        
        Returns:
            - 'no_sponsorship': explicit negative/blocker found
            - 'confirmed': explicit positive offer found
            - 'unknown': no explicit visa mention found
        """
        if not jd_text or not jd_text.strip():
            return "unknown"

        text_lower = " ".join(jd_text.lower().split())

        # 1. Check for visa blockers
        for blocker in BLOCKER_PATTERNS:
            if blocker in text_lower:
                return "no_sponsorship"

        # 2. Check for confirmed sponsorship offers
        for confirmed in CONFIRMED_PATTERNS:
            if confirmed in text_lower:
                return "confirmed"

        return "unknown"

    def evaluate(
        self,
        company: str,
        jd_text: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform comprehensive sponsorship evaluation combining company & JD signals."""
        company_conf = self.get_sponsor_confidence(company, domain)
        jd_signal = self.check_jd_sponsorship(jd_text)

        # JD explicit blocker overrides everything
        if jd_signal == "no_sponsorship":
            return {
                "company": company,
                "domain": domain,
                "company_confidence": company_conf,
                "jd_sponsorship": jd_signal,
                "sponsorship_status": "no_sponsorship",
                "is_eligible": False,
                "reason": "Job description explicitly states no visa sponsorship or citizenship required.",
            }

        # JD explicit confirmation
        if jd_signal == "confirmed":
            return {
                "company": company,
                "domain": domain,
                "company_confidence": company_conf,
                "jd_sponsorship": jd_signal,
                "sponsorship_status": "confirmed",
                "is_eligible": True,
                "reason": "Job description explicitly advertises visa sponsorship support.",
            }

        # Fallback to company level sponsorship status
        if company_conf in ("confirmed", "likely"):
            return {
                "company": company,
                "domain": domain,
                "company_confidence": company_conf,
                "jd_sponsorship": jd_signal,
                "sponsorship_status": company_conf,
                "is_eligible": True,
                "reason": f"Company {company} is a recognized H-1B sponsor with neutral JD.",
            }

        return {
            "company": company,
            "domain": domain,
            "company_confidence": company_conf,
            "jd_sponsorship": jd_signal,
            "sponsorship_status": "unknown",
            "is_eligible": False,
            "reason": f"Company {company} sponsorship history is unconfirmed and JD has no explicit visa clause.",
        }
