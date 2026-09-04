"""Auto-discover new companies from aggregator job feeds.

Scans aggregator feeds (EchoJobs, RemoteOK, Jobicy, HN) for companies not already
in the watchlist. For each unknown company, extracts board_token from job URLs,
validates the token against the ATS API, and appends to companies.yaml.
"""

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import httpx
import yaml

from src.core.models import JobPosting
from .portal_crawler import classify_portal_from_url, extract_board_token, DEFAULT_HEADERS

log = logging.getLogger(__name__)


class CompanyDiscoverer:
    """Discover new companies from aggregator job feeds and add them to the watchlist."""

    def __init__(self, companies_file: Optional[str] = None, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.companies_file = companies_file
        if not self.companies_file:
            from src.core.config import get_settings
            self.companies_file = str(get_settings().companies_yaml_path)
        self.known_domains: Set[str] = set()
        self.known_names: Set[str] = set()
        self._load_known()

    def _load_known(self) -> None:
        """Load existing company names and domains from YAML to avoid duplicates."""
        try:
            path = Path(self.companies_file)
            if not path.exists():
                return
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            companies = data.get("companies", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for comp in companies:
                if isinstance(comp, dict):
                    domain = (comp.get("domain") or "").lower().strip()
                    name = (comp.get("name") or "").lower().strip()
                    if domain:
                        self.known_domains.add(domain)
                    if name:
                        self.known_names.add(name)
        except Exception as exc:
            log.warning("Failed to load known companies: %s", exc)

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        """Extract root domain from a URL."""
        if not url:
            return None
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            # Strip www. prefix
            if host.startswith("www."):
                host = host[4:]
            # For ATS domains, extract the company domain from the URL
            # e.g. boards.greenhouse.io/acme -> acme.com (we can't know .com, but we can use the host)
            # Actually, we use the full ATS host as the key to avoid false merges
            return host if host else None
        except Exception:
            return None

    @staticmethod
    def _company_name_from_url(url: str) -> Optional[str]:
        """Derive a human-readable company name from an ATS URL."""
        if not url:
            return None
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            path_parts = [p for p in parsed.path.split("/") if p]

            # Greenhouse: boards.greenhouse.io/{token}
            if "greenhouse.io" in host and path_parts:
                return path_parts[0].replace("-", " ").replace("_", " ").title()
            # Lever: jobs.lever.co/{token}
            if "lever.co" in host and path_parts:
                return path_parts[0].replace("-", " ").replace("_", " ").title()
            # Ashby: jobs.ashbyhq.com/{token}
            if "ashbyhq.com" in host and path_parts:
                return path_parts[0].replace("-", " ").replace("_", " ").title()
            # SmartRecruiters: jobs.smartrecruiters.com/{token}
            if "smartrecruiters.com" in host and path_parts:
                return path_parts[0].replace("-", " ").replace("_", " ").title()
        except Exception:
            pass
        return None

    def _validate_token(self, portal_type: str, token: str, company_name: str) -> bool:
        """Validate that a board_token actually works against the ATS API."""
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                if portal_type == "greenhouse":
                    resp = client.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false")
                    return resp.status_code == 200
                elif portal_type == "lever":
                    resp = client.get(f"https://api.lever.co/v0/postings/{token}?mode=json")
                    return resp.status_code == 200
                elif portal_type == "ashby":
                    resp = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
                    return resp.status_code == 200
                elif portal_type == "smartrecruiters":
                    resp = client.get(f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=1&status=PUBLIC")
                    return resp.status_code == 200
                elif portal_type == "workday":
                    # Workday needs tenant + board, can't easily validate with just token
                    return False
            return False
        except Exception:
            return False

    def discover_from_aggregators(self, aggregator_jobs: List[JobPosting]) -> List[Dict[str, Any]]:
        """Find companies in aggregator feeds not in watchlist.

        Returns list of validated company dicts ready for YAML insertion.
        """
        # Group jobs by company domain
        candidates: Dict[str, Dict[str, Any]] = {}
        for job in aggregator_jobs:
            if not job.url:
                continue
            domain = self._extract_domain(job.url)
            if not domain:
                continue
            # Skip if domain already known
            if domain in self.known_domains:
                continue
            # Skip known ATS aggregator domains (not company-specific)
            ats_domains = {"echojobs.io", "remoteok.com", "jobicy.com", "news.ycombinator.com",
                           "linkedin.com", "indeed.com", "ziprecruiter.com", "glassdoor.com"}
            if domain in ats_domains or any(d in domain for d in ats_domains):
                continue

            if domain not in candidates:
                candidates[domain] = {"company": job.company, "domain": domain, "urls": [], "job_count": 0}
            candidates[domain]["urls"].append(job.url)
            candidates[domain]["job_count"] += 1

        # For each candidate, try to extract board_token and validate
        new_companies: List[Dict[str, Any]] = []
        for domain, info in candidates.items():
            # Need at least 2 jobs from same domain to be worth investigating
            if info["job_count"] < 2:
                continue

            # Derive company name: prefer from URL, fallback to job.company
            url_name = None
            for url in info["urls"][:5]:
                url_name = self._company_name_from_url(url)
                if url_name:
                    break
            company_name = url_name or info["company"]

            # Skip if name already known
            if company_name.lower() in self.known_names:
                continue

            # Try each URL to find a valid ATS token
            validated = False
            for url in info["urls"][:5]:
                portal_type = classify_portal_from_url(url)
                if portal_type == "generic":
                    continue
                token = extract_board_token(url)
                if not token:
                    continue
                if self._validate_token(portal_type, token, company_name):
                    careers_url = url.rsplit("/", 1)[0] if "/jobs/" in url else url
                    new_companies.append({
                        "name": company_name,
                        "domain": domain,
                        "portal_type": portal_type,
                        "board_token": token,
                        "enabled": True,
                        "careers_url": careers_url,
                    })
                    self.known_domains.add(domain)
                    self.known_names.add(company_name.lower())
                    validated = True
                    break

            if not validated:
                log.debug("Could not validate ATS token for %s (%s)", company_name, domain)

        return new_companies

    def add_to_yaml(self, companies: List[Dict[str, Any]]) -> None:
        """Append new companies to companies.yaml atomically (with .bak backup)."""
        if not companies:
            return

        path = Path(self.companies_file)
        if not path.exists():
            log.warning("Companies file not found: %s", self.companies_file)
            return

        # Backup
        backup_path = path.with_suffix(".yaml.bak")
        shutil.copy2(str(path), str(backup_path))

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if isinstance(data, dict):
                existing = data.get("companies", [])
            elif isinstance(data, list):
                existing = data
                data = {"companies": existing}
            else:
                data = {"companies": []}
                existing = data["companies"]

            # Append new companies
            for comp in companies:
                # Avoid exact duplicates
                if not any(
                    (c.get("name", "").lower() == comp["name"].lower()) or
                    (c.get("domain", "").lower() == comp["domain"].lower())
                    for c in existing
                ):
                    existing.append(comp)

            data["companies"] = existing

            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            log.info("Added %d new companies to %s (backup: %s)", len(companies), path, backup_path)
        except Exception as exc:
            log.error("Failed to update companies YAML: %s", exc)
            # Restore backup
            if backup_path.exists():
                shutil.copy2(str(backup_path), str(path))
                log.info("Restored backup from %s", backup_path)
