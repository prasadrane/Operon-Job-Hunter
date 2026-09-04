"""Healing strategies for self-healing agent — portal-specific fix logic.

Each strategy generates candidate fixes (alternative portal_type + board_token combinations),
validates them against real API endpoints, and returns the first working fix.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Protocol

import httpx

logger = logging.getLogger(__name__)

# Default timeout for validation probes (seconds)
PROBE_TIMEOUT = 10.0

# Common headers for HTTP requests
PROBE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


@dataclass
class CrawlerError:
    """Structured representation of a crawler failure."""

    company_name: str
    portal_type: str
    board_token: str
    error_message: str
    http_status: Optional[int] = None
    careers_url: Optional[str] = None
    timestamp: str = ""


@dataclass
class HealingCandidate:
    """A proposed fix to validate."""

    portal_type: str
    board_token: str
    reason: str = ""


@dataclass
class HealingResult:
    """Result of a healing attempt."""

    company_name: str
    original_portal: str
    original_token: str
    new_portal: Optional[str] = None
    new_token: Optional[str] = None
    success: bool = False
    validation_status: str = "pending"  # "pending", "validated", "failed"
    error: Optional[str] = None
    candidates_tried: int = 0


class HealingStrategy(Protocol):
    """Protocol for portal-specific healing strategies."""

    @property
    def name(self) -> str:
        """Strategy name for logging."""
        ...

    def can_handle(self, error: CrawlerError) -> bool:
        """Whether this strategy can attempt to fix the given error."""
        ...

    def generate_candidates(self, error: CrawlerError) -> List[HealingCandidate]:
        """Generate a list of candidate fixes to try."""
        ...


def validate_candidate(candidate: HealingCandidate, company_name: str = "") -> bool:
    """Validate a healing candidate by hitting the real API endpoint.

    Returns True if the endpoint responds successfully (200 OK with valid data).
    """
    portal = candidate.portal_type.lower()
    token = candidate.board_token

    try:
        with httpx.Client(headers=PROBE_HEADERS, timeout=PROBE_TIMEOUT, follow_redirects=True) as client:
            if portal == "greenhouse":
                url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
                resp = client.get(url)
                return resp.status_code == 200

            elif portal == "lever":
                url = f"https://api.lever.co/v0/postings/{token}?mode=json"
                resp = client.get(url)
                return resp.status_code == 200

            elif portal == "ashby":
                # Try REST API first
                url = f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
                resp = client.get(url)
                if resp.status_code == 200:
                    return True
                # Fallback to GraphQL
                graphql_url = "https://jobs.ashbyhq.com/api/non-app-graphql-endpoint"
                query = {
                    "operationName": "ApiJobBoardWithTeams",
                    "variables": {"organizationHostedJobsPageName": token},
                    "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { jobPostings { id } } }",
                }
                resp = client.post(graphql_url, json=query)
                return resp.status_code == 200

            elif portal == "workday":
                # Workday requires POST with payload
                # Try to extract tenant/board from a standard pattern
                url = f"https://{token}.wd1.myworkdayjobs.com/wday/cxs/{token}/{token}/jobs"
                payload = {"appliedFacets": {}, "limit": 1, "offset": 0}
                resp = client.post(url, json=payload)
                return resp.status_code == 200

            elif portal == "smartrecruiters":
                url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=1&status=PUBLIC"
                resp = client.get(url)
                return resp.status_code == 200

            else:
                logger.debug("Unsupported portal type for validation: %s", portal)
                return False

    except Exception as exc:
        logger.debug("Validation probe failed for %s/%s: %s", portal, token, exc)
        return False


# ─── Token Variation Generators ──────────────────────────────────────────────


def generate_token_variants(token: str, company_name: str = "") -> List[str]:
    """Generate common board token variations to try."""
    variants = set()
    variants.add(token)

    # Lowercase
    variants.add(token.lower())

    # Remove hyphens/underscores
    variants.add(token.replace("-", "").replace("_", ""))

    # Add hyphens (camelCase split)
    if token.islower() and len(token) > 5:
        # Try splitting at common boundaries
        variants.add(token.replace("inc", "-inc").replace("labs", "-labs").replace("ai", "-ai"))

    # Common suffixes
    for suffix in ["-jobs", "_jobs", "-careers", "-hq", "hq", "inc", "-inc"]:
        variants.add(f"{token}{suffix}")
        variants.add(f"{token.replace('-', '')}{suffix}")

    # Company name based
    if company_name:
        name_slug = company_name.lower().replace(" ", "").replace("-", "").replace(".", "")
        variants.add(name_slug)
        variants.add(name_slug.replace(" ", "-"))
        # Remove common words
        for word in ["inc", "llc", "corp", "company", "the", "ai"]:
            cleaned = name_slug.replace(word, "")
            if cleaned and len(cleaned) > 2:
                variants.add(cleaned)

    # Filter out empty or very short variants
    return [v for v in variants if v and len(v) >= 2]


# ─── Concrete Strategies ─────────────────────────────────────────────────────


class GreenhouseHealing:
    """When Greenhouse 404s: try Ashby, Lever, and token variations."""

    @property
    def name(self) -> str:
        return "greenhouse_healing"

    def can_handle(self, error: CrawlerError) -> bool:
        return error.portal_type.lower() == "greenhouse" and error.http_status in (404, None)

    def generate_candidates(self, error: CrawlerError) -> List[HealingCandidate]:
        candidates = []

        # 1. Try Ashby with same token
        candidates.append(HealingCandidate(
            portal_type="ashby",
            board_token=error.board_token,
            reason="Same token on Ashby",
        ))

        # 2. Try Lever with same token
        candidates.append(HealingCandidate(
            portal_type="lever",
            board_token=error.board_token,
            reason="Same token on Lever",
        ))

        # 3. Try token variations on Greenhouse
        for variant in generate_token_variants(error.board_token, error.company_name):
            if variant != error.board_token:
                candidates.append(HealingCandidate(
                    portal_type="greenhouse",
                    board_token=variant,
                    reason=f"Token variant: {variant}",
                ))

        # 4. Try Ashby with token variations
        for variant in generate_token_variants(error.board_token, error.company_name)[:5]:
            candidates.append(HealingCandidate(
                portal_type="ashby",
                board_token=variant,
                reason=f"Ashby token variant: {variant}",
            ))

        return candidates


class LeverHealing:
    """When Lever 404s: try Ashby, Greenhouse, and token variations."""

    @property
    def name(self) -> str:
        return "lever_healing"

    def can_handle(self, error: CrawlerError) -> bool:
        return error.portal_type.lower() == "lever" and error.http_status in (404, None)

    def generate_candidates(self, error: CrawlerError) -> List[HealingCandidate]:
        candidates = []

        # 1. Try Ashby with same token
        candidates.append(HealingCandidate(
            portal_type="ashby",
            board_token=error.board_token,
            reason="Same token on Ashby",
        ))

        # 2. Try Greenhouse with same token
        candidates.append(HealingCandidate(
            portal_type="greenhouse",
            board_token=error.board_token,
            reason="Same token on Greenhouse",
        ))

        # 3. Try token variations
        for variant in generate_token_variants(error.board_token, error.company_name)[:5]:
            if variant != error.board_token:
                candidates.append(HealingCandidate(
                    portal_type="lever",
                    board_token=variant,
                    reason=f"Token variant: {variant}",
                ))

        return candidates


class AshbyHealing:
    """When Ashby 404s: try token variations, fall back to Greenhouse/Lever."""

    @property
    def name(self) -> str:
        return "ashby_healing"

    def can_handle(self, error: CrawlerError) -> bool:
        return error.portal_type.lower() == "ashby" and error.http_status in (404, None)

    def generate_candidates(self, error: CrawlerError) -> List[HealingCandidate]:
        candidates = []

        # 1. Try token variations on Ashby
        for variant in generate_token_variants(error.board_token, error.company_name):
            if variant != error.board_token:
                candidates.append(HealingCandidate(
                    portal_type="ashby",
                    board_token=variant,
                    reason=f"Ashby token variant: {variant}",
                ))

        # 2. Fall back to Greenhouse with same token
        candidates.append(HealingCandidate(
            portal_type="greenhouse",
            board_token=error.board_token,
            reason="Fallback to Greenhouse",
        ))

        # 3. Fall back to Lever with same token
        candidates.append(HealingCandidate(
            portal_type="lever",
            board_token=error.board_token,
            reason="Fallback to Lever",
        ))

        return candidates


class WorkdayHealing:
    """When Workday fails: try different board names extracted from careers_url."""

    @property
    def name(self) -> str:
        return "workday_healing"

    def can_handle(self, error: CrawlerError) -> bool:
        return error.portal_type.lower() == "workday" and error.http_status in (404, 422, None)

    def generate_candidates(self, error: CrawlerError) -> List[HealingCandidate]:
        candidates = []

        # If we have a careers_url, try to extract different board names
        if error.careers_url and "myworkdayjobs.com" in error.careers_url:
            match = re.search(
                r"https://([a-zA-Z0-9_-]+)\.(wd\d+\.)?myworkdayjobs\.com/([a-zA-Z0-9_-]+)",
                error.careers_url,
            )
            if match:
                tenant = match.group(1)
                board = match.group(3)

                # Try different board name patterns
                board_variants = [
                    board,
                    board.replace("_", "-"),
                    board.replace("-", "_"),
                    f"{tenant}-careers",
                    f"{tenant}_careers",
                    "External_Career_Site",
                    "External",
                    "Jobs",
                    "Careers",
                ]

                for variant in board_variants:
                    if variant != error.board_token:
                        candidates.append(HealingCandidate(
                            portal_type="workday",
                            board_token=variant,
                            reason=f"Workday board variant: {variant}",
                        ))

        # Try token variations
        for variant in generate_token_variants(error.board_token, error.company_name)[:3]:
            if variant != error.board_token:
                candidates.append(HealingCandidate(
                    portal_type="workday",
                    board_token=variant,
                    reason=f"Workday token variant: {variant}",
                ))

        return candidates


class SmartRecruitersHealing:
    """When SmartRecruiters fails: try token variations."""

    @property
    def name(self) -> str:
        return "smartrecruiters_healing"

    def can_handle(self, error: CrawlerError) -> bool:
        return error.portal_type.lower() == "smartrecruiters" and error.http_status in (404, None)

    def generate_candidates(self, error: CrawlerError) -> List[HealingCandidate]:
        candidates = []

        # Try token variations
        for variant in generate_token_variants(error.board_token, error.company_name)[:5]:
            if variant != error.board_token:
                candidates.append(HealingCandidate(
                    portal_type="smartrecruiters",
                    board_token=variant,
                    reason=f"SmartRecruiters token variant: {variant}",
                ))

        return candidates


# ─── Strategy Registry ────────────────────────────────────────────────────────


# Ordered by priority — first match wins
HEALING_STRATEGIES: List[Any] = [
    GreenhouseHealing(),
    LeverHealing(),
    AshbyHealing(),
    WorkdayHealing(),
    SmartRecruitersHealing(),
]


def get_strategy(error: CrawlerError) -> Optional[Any]:
    """Get the appropriate healing strategy for a crawler error."""
    for strategy in HEALING_STRATEGIES:
        if strategy.can_handle(error):
            return strategy
    return None


def attempt_healing(error: CrawlerError, max_candidates: int = 10) -> HealingResult:
    """Attempt to heal a crawler error by trying candidate fixes.

    Returns a HealingResult indicating success/failure and what was tried.
    """
    result = HealingResult(
        company_name=error.company_name,
        original_portal=error.portal_type,
        original_token=error.board_token,
    )

    strategy = get_strategy(error)
    if strategy is None:
        result.error = f"No healing strategy for portal type: {error.portal_type}"
        return result

    candidates = strategy.generate_candidates(error)[:max_candidates]
    result.candidates_tried = len(candidates)

    logger.info(
        "[SelfHeal] %s: Trying %d candidates via %s",
        error.company_name,
        len(candidates),
        strategy.name,
    )

    for candidate in candidates:
        is_valid = validate_candidate(candidate, error.company_name)
        if is_valid:
            result.new_portal = candidate.portal_type
            result.new_token = candidate.board_token
            result.success = True
            result.validation_status = "validated"
            logger.info(
                "[SelfHeal] %s: Found fix — %s/%s (%s)",
                error.company_name,
                candidate.portal_type,
                candidate.board_token,
                candidate.reason,
            )
            return result

    result.validation_status = "failed"
    result.error = f"All {len(candidates)} candidates failed validation"
    logger.warning(
        "[SelfHeal] %s: No working fix found after %d candidates",
        error.company_name,
        len(candidates),
    )
    return result
