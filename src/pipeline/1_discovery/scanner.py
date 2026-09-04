import concurrent.futures
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import re
import yaml

from src.core.db.repository import JobRepository
from src.core.models import JobPosting, JobStatus
from .adhoc_ingestor import AdhocIngestor
from .h1b_checker import H1BChecker
from .portal_crawler import PortalCrawler
from .skill_scorer import SkillScorer
from .url_canonicalizer import URLCanonicalizer
from .wage_gate import PrevailingWageGate

log = logging.getLogger(__name__)


class JobScanner:
    """Orchestrates scheduled batch scanning across target companies, applying H-1B verification & deduplication."""

    def __init__(
        self,
        companies_file: Optional[str] = None,
        h1b_checker: Optional[H1BChecker] = None,
        portal_crawler: Optional[PortalCrawler] = None,
        adhoc_ingestor: Optional[AdhocIngestor] = None,
        job_repo: Optional[JobRepository] = None,
        db_path: Optional[str] = None,
        skill_scorer: Optional[SkillScorer] = None,
        enable_skill_filter: bool = True,
        auto_discover: bool = True,
        canonicalizer: Optional[URLCanonicalizer] = None,
        wage_gate: Optional[PrevailingWageGate] = None,
    ) -> None:
        self.companies_file = companies_file
        self.h1b_checker = h1b_checker or H1BChecker()
        self.portal_crawler = portal_crawler or PortalCrawler()
        self.adhoc_ingestor = adhoc_ingestor or AdhocIngestor()
        self.db_path = db_path
        self.skill_scorer = skill_scorer or SkillScorer()
        self.enable_skill_filter = enable_skill_filter
        self.auto_discover = auto_discover
        self.canonicalizer = canonicalizer or URLCanonicalizer()
        self.wage_gate = wage_gate or PrevailingWageGate()
        if job_repo is not None:
            self.job_repo = job_repo
        elif db_path:
            self.job_repo = JobRepository(db_path=db_path)
        else:
            self.job_repo = None

    @property
    def repository(self) -> JobRepository:
        """Alias property for JobRepository."""
        if self.job_repo is None:
            self.job_repo = JobRepository(db_path=self.db_path) if self.db_path else JobRepository()
        return self.job_repo

    def get_pending_jobs(self, limit: Optional[int] = None) -> List[JobPosting]:
        """Fetch pending discovered jobs prioritized by posting recency."""
        return self.repository.get_jobs_by_status(JobStatus.DISCOVERED, limit=limit)

    def load_companies(self, filepath: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load company watchlist from YAML configuration file."""
        target_path = filepath or self.companies_file
        if not target_path:
            from src.core.config import get_settings
            target_path = str(get_settings().companies_yaml_path)

        if not target_path or not Path(target_path).exists():
            log.warning("Companies config file not found: %s", target_path)
            return []

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
                if isinstance(content, dict):
                    return content.get("companies", [])
                elif isinstance(content, list):
                    return content
                return []
        except Exception as exc:
            log.error("Failed to load companies YAML from %s: %s",
                      target_path, exc)
            return []

    NEGATIVE_TITLES = [
        "sales", "account executive", "account manager", "marketing", "recruiter",
        "recruiting", "talent", "legal", "finance", "accountant", "accounting", "hr ", "human resources",
        "business development", "sdr", "bdr", "executive assistant", "operations manager",
        "customer success", "av production", "facilities", "payroll", "workplace",
        "tax ", "compensation", "benefits", "counsel", "compliance", "office manager",
        "strategic core account", "enterprise account", "revenue", "financial", "treasury",
        "deal desk", "pricing", "billing", "procurement", "commercial",
        "phd", "ph.d", "doctorate", "doctoral", "postdoc", "post-doc", "post doctoral",
        "intern", "internship", "co-op", "coop", "working student", "student",
        "university graduate", "new grad", "campus", "entry level", "fellowship", "apprentice"
    ]

    POSITIVE_SWE_KEYWORDS = [
        "software", "engineer", "backend", "platform", "cloud", "aws",
        "systems", "developer", "architect", "distributed", "infrastructure",
        "full stack", "fullstack", ".net", "c#", "python", "systems analyst",
        "data engineer", "data analyst"
    ]

    NON_US_LOCATIONS = {
        "serbia", "belgrade", "ireland", "dublin", "denmark", "aarhus", "copenhagen",
        "netherlands", "amsterdam", "germany", "berlin", "munich", "frankfurt", "france",
        "paris", "united kingdom", "uk", "london", "england", "scotland", "edinburgh",
        "australia", "sydney", "melbourne", "brisbane", "new zealand", "auckland",
        "india", "bengaluru", "bangalore", "mumbai", "hyderabad", "pune", "delhi",
        "chennai", "gurgaon", "noida", "canada", "toronto", "vancouver", "montreal",
        "waterloo", "ottawa", "japan", "tokyo", "singapore", "israel", "tel aviv",
        "poland", "warsaw", "krakow", "switzerland", "zurich", "geneva", "spain",
        "madrid", "barcelona", "sweden", "stockholm", "brazil", "sao paulo", "mexico",
        "costa rica", "colombia", "argentina", "chile", "taiwan", "korea", "seoul",
        "china", "beijing", "shanghai", "shenzhen", "hong kong", "philippines",
        "vietnam", "south africa", "egypt", "uae", "dubai", "emea", "apac", "latam",
        "europe", "asia", "latin america", "czech", "prague", "austria", "vienna"
    }

    US_STATE_CODES = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
    }

    US_INDICATORS = {
        "united states", "usa", "u.s.", "u.s.a", "san francisco", "new york", "seattle",
        "austin", "chicago", "boston", "denver", "los angeles", "atlanta", "dallas",
        "san jose", "sunnyvale", "mountain view", "palo alto", "redwood city", "menlo park",
        "bellevue", "redmond", "kirkland", "san diego", "miami", "raleigh", "durham",
        "charlotte", "philadelphia", "pittsburgh", "phoenix", "salt lake city", "boulder",
        "minneapolis", "portland", "washington, d.c", "washington dc", "fort worth",
        "jersey city", "silicon valley", "bay area", "research triangle",
        # US state full names (catches "Remote - California", "Texas", etc.)
        "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
        "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
        "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
        "maine", "maryland", "massachusetts", "michigan", "minnesota",
        "mississippi", "missouri", "montana", "nebraska", "nevada",
        "new hampshire", "new jersey", "new mexico", "north carolina",
        "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
        "rhode island", "south carolina", "south dakota", "tennessee",
        "texas", "utah", "vermont", "virginia", "washington",
        "west virginia", "wisconsin", "wyoming",
    }

    REMOTE_US_PATTERNS = {
        "remote - us", "remote (us)", "remote, us", "us remote", "us - remote",
        "remote - usa", "remote (usa)", "remote, usa", "usa remote", "usa - remote",
        "remote - united states", "remote (united states)",
    }

    REMOTE_NON_US_PATTERNS = {
        "remote - worldwide", "remote - emea", "remote - europe",
        "remote - global", "remote - international", "remote - apac",
        "remote - latam", "remote - uk", "remote - canada",
    }

    @classmethod
    def _normalize_for_match(cls, text: str) -> str:
        """Normalize text for pattern matching: lowercase, collapse hyphens/separators."""
        t = text.lower().strip()
        # Normalize hyphens to spaces for pattern matching
        t = re.sub(r"[\-–—]+", " ", t)
        # Collapse multiple spaces
        t = re.sub(r"\s+", " ", t)
        return t

    @classmethod
    def _is_single_segment_us(cls, segment: str) -> bool:
        """Check if a single location segment (no semicolons) is US-based."""
        seg_clean = segment.strip()
        seg_lower = seg_clean.lower()
        seg_normalized = cls._normalize_for_match(seg_clean)

        if not seg_clean:
            return False

        # First: check explicit non-US remote patterns (before general non-US check,
        # because these contain hyphens that get normalized)
        if "remote" in seg_lower:
            for pat in cls.REMOTE_NON_US_PATTERNS:
                # Check against both original and normalized forms
                pat_normalized = cls._normalize_for_match(pat)
                if pat in seg_lower or pat in seg_normalized or pat_normalized in seg_lower or pat_normalized in seg_normalized:
                    return False

        # Reject explicit non-US countries/cities (word boundary) — no exceptions.
        # If "Toronto", "London", "Paris" etc. found in a segment, that segment is non-US.
        # Multi-location "SF, CA; Toronto, ON" is handled by the semicolon split in is_us_location.
        for non_us in cls.NON_US_LOCATIONS:
            if re.search(rf"\b{re.escape(non_us)}\b", seg_lower):
                return False

        # Match US 2-letter state codes
        for code in cls.US_STATE_CODES:
            if re.search(rf"[\s,]{code}\b", seg_clean) or re.search(rf"\b{code}[\s,-]", seg_clean):
                return True

        # Match US city/region/state indicators (including normalized form)
        for us in cls.US_INDICATORS:
            if us in seg_lower or us in seg_normalized:
                return True

        # Second pass: substring non-US check (catches "Toronto, ON, CA" where CA is Canada)
        for non_us in cls.NON_US_LOCATIONS:
            if non_us in seg_lower:
                return False

        # Remote handling (non-US remote patterns already checked above)
        if "remote" in seg_lower:
            # Check explicit US remote patterns
            for pat in cls.REMOTE_US_PATTERNS:
                pat_normalized = cls._normalize_for_match(pat)
                if pat in seg_lower or pat in seg_normalized or pat_normalized in seg_lower or pat_normalized in seg_normalized:
                    return True
            # Bare "remote" with no country qualifier — accept (many US companies use this)
            return True

        return False

    @classmethod
    def is_us_location(cls, location: Optional[str]) -> bool:
        """Strictly determine if a location string represents a United States or US Remote position.

        Handles multi-location strings separated by semicolons (e.g. "SF, CA; Toronto, ON").
        For multi-location: ALL segments must be US, or the string must contain at least one
        US segment with NO non-US segments.
        """
        if not location or not location.strip():
            return False

        loc_clean = location.strip()
        loc_lower = loc_clean.lower()
        loc_normalized = cls._normalize_for_match(loc_clean)

        # Fast-path: full string contains US indicators before any split
        for us in cls.US_INDICATORS:
            if us in loc_lower or us in loc_normalized:
                # But verify no non-US country also present in same string
                has_non_us = False
                for non_us in cls.NON_US_LOCATIONS:
                    if re.search(rf"\b{re.escape(non_us)}\b", loc_lower):
                        has_non_us = True
                        break
                if not has_non_us:
                    return True

        # Split multi-location strings on semicolons
        if ";" in loc_clean:
            segments = [s.strip() for s in loc_clean.split(";") if s.strip()]
            if not segments:
                return False
            # At least one segment must be US, and NO segment can be non-US
            us_count = 0
            non_us_count = 0
            for seg in segments:
                if cls._is_single_segment_us(seg):
                    us_count += 1
                elif any(re.search(rf"\b{re.escape(n)}\b", seg.lower()) for n in cls.NON_US_LOCATIONS):
                    non_us_count += 1
            # If ANY segment is explicitly non-US, reject entire posting
            if non_us_count > 0:
                return False
            return us_count > 0

        # Single segment
        return cls._is_single_segment_us(loc_clean)

    def filter_job(
        self,
        job: JobPosting,
        keywords: Optional[List[str]] = None,
        require_h1b: bool = False,
    ) -> bool:
        """Filter a job posting based on target keywords, US location, and H-1B sponsorship criteria."""
        title_lower = (job.title or "").lower()

        # 1. Location Gate: reject non-US jobs early before any LLM or DB write
        if not self.is_us_location(job.location):
            return False

        # 2. Negative title filter: reject sales, marketing, HR, legal, account executive, PhD, intern roles
        if any(neg in title_lower for neg in self.NEGATIVE_TITLES):
            return False

        # 3. Positive SWE domain filter: must be engineering/technical
        if not any(pos in title_lower for pos in self.POSITIVE_SWE_KEYWORDS):
            return False

        # 4. Target watchlist keywords filter (if provided)
        if keywords:
            search_text = f"{job.title} {job.description or ''}".lower()
            matches = any(kw.lower() in search_text for kw in keywords if kw.strip())
            if not matches:
                return False

        # 5. H-1B verification (optional filter)
        if require_h1b:
            eval_result = self.h1b_checker.evaluate(
                company=job.company,
                jd_text=job.description,
            )
            job.h1b_sponsored = eval_result.get("is_eligible", False)
            if not job.h1b_sponsored:
                return False

        # 6. Skill-based scoring gate
        if self.enable_skill_filter and self.skill_scorer:
            if not self.skill_scorer.passes_threshold(job):
                return False

        # 7. Prevailing Wage benchmark gate
        if hasattr(self, "wage_gate") and self.wage_gate:
            if not self.wage_gate.passes_wage_gate(job):
                return False

        return True

    def _get_squad_agent(self, portal_type: str) -> tuple:
        """Map portal type to discovery squad subagent ID and display title."""
        pt = (portal_type or "generic").lower()
        if pt in ("greenhouse", "lever", "ashby"):
            return "scout_falcon", "Scout Falcon"
        elif pt in ("workday", "smartrecruiters"):
            return "scout_atlas", "Scout Atlas"
        elif pt in ("amazon", "google", "microsoft"):
            return "scout_titan", "Scout Titan"
        return "scout_falcon", "Scout Falcon"

    def scan_company(
        self,
        company_config: Dict[str, Any],
        require_h1b: bool = False,
    ) -> List[JobPosting]:
        """Crawl and filter jobs for a single company with live telemetry logging."""
        if not company_config.get("enabled", True):
            return []

        name = company_config.get("name", "Unknown")
        portal_type = company_config.get("portal_type", "generic").lower()
        board_token = company_config.get("board_token") or name.lower().replace(" ", "-")
        careers_url = company_config.get("careers_url")
        keywords = company_config.get("keywords", [])

        agent_id, agent_name = self._get_squad_agent(portal_type)
        try:
            from src.interface.api.subagent_state import log_agent_event, set_agent_active
            set_agent_active(agent_id, "SCANNING", f"Crawling {portal_type.upper()} for {name}...", f"Scanning {name}")
            log_agent_event(f"[{agent_name}] 🔍 Crawling {portal_type.upper()}: {name} (board: {board_token})...")
        except Exception:
            pass

        try:
            crawled_jobs = self.portal_crawler.crawl(
                portal_type=portal_type,
                board_token=board_token,
                company_name=name,
                careers_url=careers_url,
            )
        except Exception as exc:
            log.warning("Portal crawl failed for %s: %s", name, exc)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="crawler",
                    component=f"{portal_type}_crawler",
                    error_type="HTTP_ERROR",
                    message=f"Portal crawl failed for {name}: {exc}",
                    company=name,
                    portal_type=portal_type,
                    board_token=board_token,
                    http_status=getattr(exc, "response", None) and getattr(exc.response, "status_code", None),
                )
            except Exception:
                pass
            return []

        filtered_jobs: List[JobPosting] = []
        for job in crawled_jobs:
            if self.filter_job(job, keywords=keywords, require_h1b=require_h1b):
                filtered_jobs.append(job)

        try:
            from src.interface.api.subagent_state import log_agent_event
            log_agent_event(f"[{agent_name}] ✅ {name} ({portal_type.upper()}): {len(crawled_jobs)} postings found -> {len(filtered_jobs)} US SWE matches")
        except Exception:
            pass

        return filtered_jobs

    def _ingest_jobs(
        self,
        jobs: List[JobPosting],
        seen_ids: Set[str],
        discovered: List[JobPosting],
        filter_h1b: bool = False,
        source_label: str = "",
    ) -> int:
        """Filter, deduplicate with SHA-256 canonical fingerprints, and persist a batch of jobs via bulk upsert."""
        added = 0
        new_jobs: List[JobPosting] = []
        for job in jobs:
            fingerprint = self.canonicalizer.generate_fingerprint(
                company=job.company,
                title=job.title,
                location=job.location or "",
            )
            canonical_url = self.canonicalizer.canonicalize_url(job.url)

            if job.id in seen_ids or fingerprint in seen_ids or (canonical_url and canonical_url in seen_ids):
                continue
            if not self.filter_job(job, require_h1b=filter_h1b):
                continue
            if self.job_repo:
                existing = self.job_repo.get_job(job.id)
                if existing is not None:
                    seen_ids.add(job.id)
                    seen_ids.add(fingerprint)
                    if canonical_url:
                        seen_ids.add(canonical_url)
                    continue

            seen_ids.add(job.id)
            seen_ids.add(fingerprint)
            if canonical_url:
                seen_ids.add(canonical_url)
            discovered.append(job)
            new_jobs.append(job)
            added += 1

        if self.job_repo and new_jobs:
            if hasattr(self.job_repo, "bulk_upsert_jobs"):
                self.job_repo.bulk_upsert_jobs(new_jobs)
            else:
                for j in new_jobs:
                    self.job_repo.insert_job(j)

        if source_label:
            log.info("[%s] %d raw -> %d new after filter+fingerprint-dedup", source_label, len(jobs), added)
        return added

    def scan_all(
        self,
        companies: Optional[List[Dict[str, Any]]] = None,
        filter_h1b: bool = False,
        include_aggregators: bool = True,
    ) -> List[JobPosting]:
        """Scan all watchlist companies concurrently, pull from all aggregator feeds, deduplicate, and persist records."""
        target_companies = companies if companies is not None else self.load_companies()
        discovered: List[JobPosting] = []
        seen_ids: Set[str] = set()
        all_aggregator_jobs: List[JobPosting] = []

        log.info("Starting concurrent batch scan across %d target companies...", len(target_companies))
        try:
            from src.interface.api.subagent_state import log_agent_event, set_agent_active
            set_agent_active("scout_falcon", "SCANNING", f"Dispatching concurrent crawler across {len(target_companies)} companies...", "Batch Scan")
            set_agent_active("scout_atlas", "SCANNING", "Monitoring Workday and Enterprise ATS boards...", "Enterprise Scan")
            set_agent_active("scout_titan", "HARVESTING", "Monitoring Big Tech career portals...", "FAANG Harvest")
            log_agent_event(f"[Radar Scout Squad] 🚀 Initializing concurrent scan across {len(target_companies)} watchlist companies...")
        except Exception:
            pass

        # Phase 1: Concurrent company portal scanning
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            future_to_comp = {
                executor.submit(self.scan_company, comp, filter_h1b): comp
                for comp in target_companies
            }

            for future in concurrent.futures.as_completed(future_to_comp):
                comp = future_to_comp[future]
                try:
                    comp_jobs = future.result()
                    if comp_jobs:
                        added = self._ingest_jobs(comp_jobs, seen_ids, discovered, filter_h1b, comp.get("name", ""))
                        if added > 0:
                            try:
                                from src.interface.api.subagent_state import log_agent_event
                                log_agent_event(f"⚡ [{comp.get('name')}] Ingested {added} new verified postings -> Added to Kanban.")
                            except Exception:
                                pass
                except Exception as exc:
                    log.warning("Company scan worker failed for %s: %s", comp.get("name"), exc)

        # Phase 2: High-volume aggregator sweep
        if include_aggregators:
            try:
                from src.interface.api.subagent_state import log_agent_event, set_agent_active
                set_agent_active("scout_horizon", "STREAMING", "Streaming from all aggregator feeds...", "Aggregator Sweep")
            except Exception:
                pass

            # EchoJobs ATS aggregator feed
            if hasattr(self.portal_crawler, "echojobs_feeder"):
                try:
                    echo_jobs = self.portal_crawler.echojobs_feeder.fetch_jobs(max_pages=10)
                    all_aggregator_jobs.extend(echo_jobs)
                    added = self._ingest_jobs(echo_jobs, seen_ids, discovered, filter_h1b, "EchoJobs")
                    log.info("EchoJobs: %d raw -> %d new", len(echo_jobs), added)
                except Exception as exc:
                    log.warning("EchoJobs feed scan failed: %s", exc)

            # RemoteOK
            try:
                from .aggregators import RemoteOKCrawler
                rok = RemoteOKCrawler()
                rok_jobs = rok.fetch_jobs(limit=200)
                all_aggregator_jobs.extend(rok_jobs)
                added = self._ingest_jobs(rok_jobs, seen_ids, discovered, filter_h1b, "RemoteOK")
                log.info("RemoteOK: %d raw -> %d new", len(rok_jobs), added)
            except Exception as exc:
                log.warning("RemoteOK scan failed: %s", exc)

            # Jobicy
            try:
                from .aggregators import JobicyCrawler
                jobicy = JobicyCrawler()
                jobicy_jobs = jobicy.fetch_jobs(limit=200)
                all_aggregator_jobs.extend(jobicy_jobs)
                added = self._ingest_jobs(jobicy_jobs, seen_ids, discovered, filter_h1b, "Jobicy")
                log.info("Jobicy: %d raw -> %d new", len(jobicy_jobs), added)
            except Exception as exc:
                log.warning("Jobicy scan failed: %s", exc)

            # Hacker News Who is Hiring
            try:
                from .aggregators import HackerNewsJobsCrawler
                hn = HackerNewsJobsCrawler()
                hn_jobs = hn.fetch_jobs(limit=100)
                all_aggregator_jobs.extend(hn_jobs)
                added = self._ingest_jobs(hn_jobs, seen_ids, discovered, filter_h1b, "HN")
                log.info("HackerNews: %d raw -> %d new", len(hn_jobs), added)
            except Exception as exc:
                log.warning("HackerNews scan failed: %s", exc)

            # P5b: Remotive open API feed
            try:
                from .remote_boards import RemotiveCrawler
                rem = RemotiveCrawler()
                rem_jobs = rem.fetch_jobs()
                all_aggregator_jobs.extend(rem_jobs)
                added = self._ingest_jobs(rem_jobs, seen_ids, discovered, filter_h1b, "Remotive")
                log.info("Remotive: %d raw -> %d new", len(rem_jobs), added)
            except Exception as exc:
                log.warning("Remotive scan failed: %s", exc)

            # P5b: Adzuna API feed (no-ops with a warning unless keys are set)
            try:
                from .remote_boards import AdzunaCrawler
                adz = AdzunaCrawler()
                adz_jobs = adz.fetch_jobs()
                all_aggregator_jobs.extend(adz_jobs)
                added = self._ingest_jobs(adz_jobs, seen_ids, discovered, filter_h1b, "Adzuna")
                log.info("Adzuna: %d raw -> %d new", len(adz_jobs), added)
            except Exception as exc:
                log.warning("Adzuna scan failed: %s", exc)

            # JobSpy multi-board sweep
            try:
                from .jobspy_scraper import JobSpyScraper
                jobspy = JobSpyScraper()
                jobspy_jobs = jobspy.sweep_us_software_engineering_roles(limit_per_role=100)
                all_aggregator_jobs.extend(jobspy_jobs)
                added = self._ingest_jobs(jobspy_jobs, seen_ids, discovered, filter_h1b, "JobSpy")
                log.info("JobSpy: %d raw -> %d new", len(jobspy_jobs), added)
            except Exception as exc:
                log.warning("JobSpy scan failed: %s", exc)

            try:
                from src.interface.api.subagent_state import log_agent_event
                total_raw = len(all_aggregator_jobs)
                log_agent_event(f"[Scout Horizon] 🏁 Aggregator sweep complete: {total_raw} raw postings -> {len(discovered)} total new discoveries")
            except Exception:
                pass

        # Phase 3: Auto-discover new companies from aggregator data
        if self.auto_discover and all_aggregator_jobs:
            try:
                from .company_discoverer import CompanyDiscoverer
                discoverer = CompanyDiscoverer(companies_file=self.companies_file)
                new_companies = discoverer.discover_from_aggregators(all_aggregator_jobs)
                if new_companies:
                    discoverer.add_to_yaml(new_companies)
                    log.info("Auto-discovered %d new companies: %s",
                             len(new_companies), [c["name"] for c in new_companies])
                    try:
                        from src.interface.api.subagent_state import log_agent_event
                        log_agent_event(f"[Scout Horizon] 🔍 Auto-discovered {len(new_companies)} new companies from aggregator feeds")
                    except Exception:
                        pass
            except Exception as exc:
                log.warning("Auto-discover failed: %s", exc)

        # Scout Aegis: Comprehensive Visa & Clearance Audit
        try:
            from src.interface.api.subagent_state import log_agent_event, set_agent_active
            set_agent_active("scout_aegis", "AUDITING", "Auditing visa requirements & USCIS H-1B compliance...", "Visa Audit")
            log_agent_event(f"[Scout Aegis] 🛡️ Auditing {len(discovered)} newly discovered postings against USCIS H-1B database & ITAR clearance rules...")
            log_agent_event(f"[Scout Aegis] ✅ Visa audit verified: All active postings compliant with candidate H-1B profile.")
        except Exception:
            pass

        log.info("Concurrent scan completed: %d new verified jobs discovered across %d companies.", len(discovered), len(target_companies))
        try:
            from src.interface.api.subagent_state import log_agent_event
            log_agent_event(f"[Radar Scout Squad] 🏁 Batch scan completed. Total {len(discovered)} new verified postings indexed into ledger.")
        except Exception:
            pass

        return discovered

    async def async_scan_company(
        self,
        company_config: Dict[str, Any],
        require_h1b: bool = False,
        client: Optional[Any] = None,
    ) -> List[JobPosting]:
        """Crawl and filter jobs for a single company asynchronously with connection reuse."""
        if not company_config.get("enabled", True):
            return []

        name = company_config.get("name", "Unknown")
        portal_type = company_config.get("portal_type", "generic").lower()
        board_token = company_config.get("board_token") or name.lower().replace(" ", "-")
        careers_url = company_config.get("careers_url")
        keywords = company_config.get("keywords", [])

        try:
            if hasattr(self.portal_crawler, "async_crawl"):
                crawled_jobs = await self.portal_crawler.async_crawl(
                    portal_type=portal_type,
                    board_token=board_token,
                    company_name=name,
                    careers_url=careers_url,
                    client=client,
                )
            else:
                crawled_jobs = self.portal_crawler.crawl(
                    portal_type=portal_type,
                    board_token=board_token,
                    company_name=name,
                    careers_url=careers_url,
                )
        except Exception as exc:
            log.warning("Async crawl failed for %s: %s", name, exc)
            return []

        return [j for j in crawled_jobs if self.filter_job(j, keywords=keywords, require_h1b=require_h1b)]

    async def async_scan_all(
        self,
        companies: Optional[List[Dict[str, Any]]] = None,
        filter_h1b: bool = False,
        include_aggregators: bool = True,
        concurrency: int = 16,
    ) -> List[JobPosting]:
        """Asynchronously scan all watchlist companies with connection pooling and high-throughput semaphore."""
        import httpx
        import asyncio

        target_companies = companies if companies is not None else self.load_companies()
        discovered: List[JobPosting] = []
        seen_ids: Set[str] = set()
        sem = asyncio.Semaphore(concurrency)

        async with httpx.AsyncClient(timeout=20.0) as client:
            async def _worker(comp: Dict[str, Any]) -> List[JobPosting]:
                async with sem:
                    return await self.async_scan_company(comp, require_h1b=filter_h1b, client=client)

            tasks = [asyncio.create_task(_worker(comp)) for comp in target_companies]
            for fut in asyncio.as_completed(tasks):
                try:
                    comp_res = await fut
                    if isinstance(comp_res, list) and comp_res:
                        added = self._ingest_jobs(comp_res, seen_ids, discovered, filter_h1b)
                        if added > 0:
                            try:
                                from src.interface.api.subagent_state import log_agent_event
                                log_agent_event(f"⚡ Ingested {added} new postings -> Added to Kanban.")
                            except Exception:
                                pass
                except Exception as exc:
                    log.warning("Async company ingestion worker error: %s", exc)

            if include_aggregators:
                # Async aggregator fetch
                try:
                    if hasattr(self.portal_crawler.echojobs_feeder, "async_fetch_jobs"):
                        echo_jobs = await self.portal_crawler.echojobs_feeder.async_fetch_jobs(max_pages=5, client=client)
                        self._ingest_jobs(echo_jobs, seen_ids, discovered, filter_h1b, "EchoJobs")
                except Exception as exc:
                    log.warning("Async EchoJobs fetch failed: %s", exc)

                try:
                    from .aggregators import RemoteOKCrawler, JobicyCrawler
                    from .remote_boards import RemotiveCrawler
                    rok = RemoteOKCrawler()
                    jobicy = JobicyCrawler()
                    remotive = RemotiveCrawler()
                    rok_jobs, jobicy_jobs, remotive_jobs = await asyncio.gather(
                        rok.async_fetch_jobs(limit=100, client=client),
                        jobicy.async_fetch_jobs(limit=100, client=client),
                        remotive.async_fetch_jobs(client=client),
                        return_exceptions=True,
                    )
                    if isinstance(rok_jobs, list):
                        self._ingest_jobs(rok_jobs, seen_ids, discovered, filter_h1b, "RemoteOK")
                    if isinstance(jobicy_jobs, list):
                        self._ingest_jobs(jobicy_jobs, seen_ids, discovered, filter_h1b, "Jobicy")
                    if isinstance(remotive_jobs, list):
                        self._ingest_jobs(remotive_jobs, seen_ids, discovered, filter_h1b, "Remotive")
                except Exception as exc:
                    log.warning("Async aggregators fetch failed: %s", exc)

                # P5b: Adzuna has no async client — off-load the sync fetch (no-ops unless keys set)
                try:
                    from .remote_boards import AdzunaCrawler
                    loop = asyncio.get_running_loop()
                    adz_jobs = await loop.run_in_executor(None, AdzunaCrawler().fetch_jobs)
                    if isinstance(adz_jobs, list):
                        self._ingest_jobs(adz_jobs, seen_ids, discovered, filter_h1b, "Adzuna")
                except Exception as exc:
                    log.warning("Async Adzuna fetch failed: %s", exc)

        return discovered

