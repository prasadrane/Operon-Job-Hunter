"""Discovery Healer — auto-fixes crawler configuration errors.

Handles HTTP_404, HTTP_422 errors from the discovery/crawler stage by:
- Trying alternative ATS portals (greenhouse↔ashby↔lever)
- Generating board token variations
- Validating candidates against real API endpoints
- Updating companies.yaml with the fix
"""

from dataclasses import dataclass
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseHealer, HealingResult

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 10.0
PROBE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
}


# ─── Token Variation Generator ───────────────────────────────────────────────


def generate_token_variants(token: str, company_name: str = "") -> List[str]:
    """Generate common board token variations to try."""
    variants = set()
    variants.add(token)
    variants.add(token.lower())
    variants.add(token.replace("-", "").replace("_", ""))

    if token.islower() and len(token) > 5:
        variants.add(token.replace("inc", "-inc").replace("labs", "-labs").replace("ai", "-ai"))

    for suffix in ["-jobs", "_jobs", "-careers", "-hq", "hq", "inc", "-inc"]:
        variants.add(f"{token}{suffix}")
        variants.add(f"{token.replace('-', '')}{suffix}")

    if company_name:
        name_slug = company_name.lower().replace(" ", "").replace("-", "").replace(".", "")
        variants.add(name_slug)
        for word in ["inc", "llc", "corp", "company", "the", "ai"]:
            cleaned = name_slug.replace(word, "")
            if cleaned and len(cleaned) > 2:
                variants.add(cleaned)

    return [v for v in variants if v and len(v) >= 2]


# ─── Candidate Validation ────────────────────────────────────────────────────


@dataclass
class HealingCandidate:
    portal_type: str
    board_token: str
    reason: str = ""


def validate_candidate(candidate: HealingCandidate) -> bool:
    """Validate a healing candidate by hitting the real API endpoint."""
    portal = candidate.portal_type.lower()
    token = candidate.board_token

    try:
        with httpx.Client(headers=PROBE_HEADERS, timeout=PROBE_TIMEOUT, follow_redirects=True) as client:
            if portal == "greenhouse":
                url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
                return client.get(url).status_code == 200

            elif portal == "lever":
                url = f"https://api.lever.co/v0/postings/{token}?mode=json"
                return client.get(url).status_code == 200

            elif portal == "ashby":
                url = f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
                resp = client.get(url)
                if resp.status_code == 200:
                    return True
                graphql_url = "https://jobs.ashbyhq.com/api/non-app-graphql-endpoint"
                query = {
                    "operationName": "ApiJobBoardWithTeams",
                    "variables": {"organizationHostedJobsPageName": token},
                    "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { jobPostings { id } } }",
                }
                return client.post(graphql_url, json=query).status_code == 200

            elif portal == "smartrecruiters":
                url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=1&status=PUBLIC"
                return client.get(url).status_code == 200

            elif portal == "workday":
                url = f"https://{token}.wd1.myworkdayjobs.com/wday/cxs/{token}/jobs"
                return client.post(url, json={"appliedFacets": {}, "limit": 1, "offset": 0}).status_code == 200

            return False

    except Exception:
        return False


# ─── Strategy: Generate Candidates per Portal Type ───────────────────────────


def _greenhouse_candidates(token: str, company: str) -> List[HealingCandidate]:
    cands = [
        HealingCandidate("ashby", token, "Same token on Ashby"),
        HealingCandidate("lever", token, "Same token on Lever"),
    ]
    for v in generate_token_variants(token, company)[:5]:
        if v != token:
            cands.append(HealingCandidate("greenhouse", v, f"Token variant: {v}"))
    for v in generate_token_variants(token, company)[:3]:
        cands.append(HealingCandidate("ashby", v, f"Ashby token variant: {v}"))
    return cands


def _lever_candidates(token: str, company: str) -> List[HealingCandidate]:
    cands = [
        HealingCandidate("ashby", token, "Same token on Ashby"),
        HealingCandidate("greenhouse", token, "Same token on Greenhouse"),
    ]
    for v in generate_token_variants(token, company)[:5]:
        if v != token:
            cands.append(HealingCandidate("lever", v, f"Token variant: {v}"))
    return cands


def _ashby_candidates(token: str, company: str) -> List[HealingCandidate]:
    cands = []
    for v in generate_token_variants(token, company):
        if v != token:
            cands.append(HealingCandidate("ashby", v, f"Ashby token variant: {v}"))
    cands.append(HealingCandidate("greenhouse", token, "Fallback to Greenhouse"))
    cands.append(HealingCandidate("lever", token, "Fallback to Lever"))
    return cands


def _workday_candidates(token: str, company: str, careers_url: Optional[str]) -> List[HealingCandidate]:
    cands = []
    if careers_url and "myworkdayjobs.com" in careers_url:
        match = re.search(r"https://([a-zA-Z0-9_-]+)\.(wd\d+\.)?myworkdayjobs\.com/([a-zA-Z0-9_-]+)", careers_url)
        if match:
            tenant = match.group(1)
            board = match.group(3)
            for variant in [board, board.replace("_", "-"), board.replace("-", "_"),
                            f"{tenant}-careers", "External_Career_Site", "External", "Jobs"]:
                if variant != token:
                    cands.append(HealingCandidate("workday", variant, f"Workday board variant: {variant}"))
    for v in generate_token_variants(token, company)[:3]:
        if v != token:
            cands.append(HealingCandidate("workday", v, f"Workday token variant: {v}"))
    return cands


def _smartrecruiters_candidates(token: str, company: str) -> List[HealingCandidate]:
    return [
        HealingCandidate("smartrecruiters", v, f"Token variant: {v}")
        for v in generate_token_variants(token, company)[:5]
        if v != token
    ]


STRATEGY_MAP = {
    "greenhouse": _greenhouse_candidates,
    "lever": _lever_candidates,
    "ashby": _ashby_candidates,
    "workday": _workday_candidates,
    "smartrecruiters": _smartrecruiters_candidates,
}


# ─── YAML Config Update ─────────────────────────────────────────────────────


def _load_companies_yaml(filepath: str) -> List[Dict[str, Any]]:
    import yaml
    with open(filepath, "r", encoding="utf-8") as f:
        content = yaml.safe_load(f)
        if isinstance(content, dict):
            return content.get("companies", [])
        elif isinstance(content, list):
            return content
        return []


def _save_companies_yaml(filepath: str, companies: List[Dict[str, Any]]) -> None:
    import os
    import shutil
    import tempfile
    import yaml
    from pathlib import Path

    path = Path(filepath)
    bak_path = path.with_suffix(".yaml.bak")
    if path.exists():
        shutil.copy2(str(path), str(bak_path))

    dir_name = path.parent
    # Load existing YAML to preserve all top-level keys (version, metadata, etc.)
    existing_data: Dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    existing_data = loaded
        except Exception:
            existing_data = {}

    fd, tmp_path = tempfile.mkstemp(dir=str(dir_name), suffix=".yaml.tmp")
    try:
        existing_data["companies"] = companies
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(existing_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        with open(tmp_path, "r", encoding="utf-8") as f:
            yaml.safe_load(f)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _update_company_config(filepath: str, company_name: str, updates: Dict[str, Any]) -> bool:
    try:
        companies = _load_companies_yaml(filepath)
        for company in companies:
            if company.get("name", "").lower() == company_name.lower():
                company.update(updates)
                _save_companies_yaml(filepath, companies)
                return True
            if company.get("board_token", "").lower() == company_name.lower():
                company.update(updates)
                _save_companies_yaml(filepath, companies)
                return True
        return False
    except Exception as exc:
        logger.error("[DiscoveryHealer] Failed to update config: %s", exc)
        return False


# ─── Discovery Healer ────────────────────────────────────────────────────────


class DiscoveryHealer(BaseHealer):
    """Auto-fixes crawler configuration errors by trying alternative ATS portals
    and board token variations."""

    name = "discovery"
    stage_label = "Discovery/Crawler"
    source = "crawler"

    def __init__(
        self,
        companies_file: Optional[str] = None,
        max_candidates: int = 10,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if not companies_file:
            from src.core.config import get_settings
            companies_file = str(get_settings().companies_yaml_path)
        self.companies_file = companies_file
        self.max_candidates = max_candidates

    def can_heal(self, error_type: str, component: str) -> bool:
        return error_type in ("HTTP_404", "HTTP_422", "HTTP_ERROR")

    def heal(self, errors: List[Any]) -> List[HealingResult]:
        results = []
        seen = set()

        for error in errors:
            company = getattr(error, "company", None) or getattr(error, "component", "")
            portal = getattr(error, "portal_type", "greenhouse")
            token = getattr(error, "board_token", "")
            careers_url = getattr(error, "careers_url", None)
            error_id = getattr(error, "id", None)

            if not token or company in seen:
                continue
            seen.add(company)

            # Get company config to enrich
            config = self._get_company_config(company)
            if config:
                portal = config.get("portal_type", portal)
                token = config.get("board_token", token)
                careers_url = careers_url or config.get("careers_url")

            # Generate candidates based on strategy
            strategy_fn = STRATEGY_MAP.get(portal.lower())
            if not strategy_fn:
                results.append(HealingResult(
                    healer=self.name,
                    action=f"No strategy for portal type: {portal}",
                    success=False,
                    company=company,
                    error_id=error_id,
                ))
                continue

            candidates = strategy_fn(token, company, careers_url) if portal.lower() == "workday" else strategy_fn(token, company)
            candidates = candidates[:self.max_candidates]

            # Try each candidate
            healed = False
            for cand in candidates:
                if validate_candidate(cand):
                    if self.dry_run:
                        logger.info("[DiscoveryHealer] DRY RUN: %s → %s/%s (%s)",
                                    company, cand.portal_type, cand.board_token, cand.reason)
                        results.append(HealingResult(
                            healer=self.name,
                            action=f"Would update {company}: {portal}/{token} → {cand.portal_type}/{cand.board_token} ({cand.reason})",
                            success=True,
                            company=company,
                            error_id=error_id,
                            config_changed=False,
                            details={"from": {"portal_type": portal, "board_token": token},
                                     "to": {"portal_type": cand.portal_type, "board_token": cand.board_token}},
                        ))
                    else:
                        ok = _update_company_config(self.companies_file, company, {
                            "portal_type": cand.portal_type,
                            "board_token": cand.board_token,
                        })
                        if ok:
                            self._broadcast(
                                f"Fixed {company}: {portal}/{token} → {cand.portal_type}/{cand.board_token}"
                            )
                            results.append(HealingResult(
                                healer=self.name,
                                action=f"Updated {company}: {portal}/{token} → {cand.portal_type}/{cand.board_token}",
                                success=True,
                                company=company,
                                error_id=error_id,
                                config_changed=True,
                                details={"from": {"portal_type": portal, "board_token": token},
                                         "to": {"portal_type": cand.portal_type, "board_token": cand.board_token}},
                            ))
                            healed = True
                            break

            if not healed and not self.dry_run:
                results.append(HealingResult(
                    healer=self.name,
                    action=f"No working fix found for {company} ({portal}/{token})",
                    success=False,
                    company=company,
                    error_id=error_id,
                ))

            if len(results) >= self.max_heal_per_cycle:
                break

        return results

    def _get_company_config(self, company_name: str) -> Optional[Dict[str, Any]]:
        try:
            companies = _load_companies_yaml(self.companies_file)
            for c in companies:
                if c.get("name", "").lower() == company_name.lower():
                    return c
                if c.get("board_token", "").lower() == company_name.lower():
                    return c
        except Exception:
            pass
        return None
