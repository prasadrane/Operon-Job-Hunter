"""DOL Prevailing Wage Early Gating for Senior Software Engineering Roles."""

import logging
import re
from typing import Optional
from src.core.models import JobPosting

log = logging.getLogger(__name__)

# Regular expressions for salary extraction ($140,000 - $190,000 or $140k - $190k)
SALARY_RANGE_RE = re.compile(
    r"\$\s*(\d{2,3}(?:,\d{3})*|\d{2,3})\s*(?:k|K)?\s*(?:-|–|to)\s*\$?\s*(\d{2,3}(?:,\d{3})*|\d{2,3})\s*(?:k|K)?",
)
SINGLE_SALARY_RE = re.compile(
    r"\$\s*(\d{2,3}(?:,\d{3})*|\d{2,3})\s*(?:k|K)?(?:\s*/?\s*(?:yr|year|annual|annually))?",
)


class PrevailingWageGate:
    """Gates discovered job postings against DOL OEWS prevailing wage benchmarks for senior software engineers."""

    def __init__(self, min_salary_threshold: float = 110000.0) -> None:
        self.min_salary_threshold = min_salary_threshold

    def extract_salary_bounds(self, text: str) -> Optional[tuple[float, float]]:
        """Extract minimum and maximum annual salary from job description."""
        if not text:
            return None

        # Check for range: $140,000 - $180,000
        match_range = SALARY_RANGE_RE.search(text)
        if match_range:
            raw_min = match_range.group(1).replace(",", "")
            raw_max = match_range.group(2).replace(",", "")
            val_min = float(raw_min) * 1000 if float(raw_min) < 1000 else float(raw_min)
            val_max = float(raw_max) * 1000 if float(raw_max) < 1000 else float(raw_max)
            return (val_min, val_max)

        # Check single salary
        match_single = SINGLE_SALARY_RE.search(text)
        if match_single:
            raw_val = match_single.group(1).replace(",", "")
            val = float(raw_val) * 1000 if float(raw_val) < 1000 else float(raw_val)
            if val >= 40000:  # Filter out hourly rates like $80
                return (val, val)

        return None

    def passes_wage_gate(self, job: JobPosting) -> bool:
        """Evaluate if posting meets prevailing wage minimum threshold. Postings without salary pass through."""
        text = f"{job.title} {job.description or ''}"
        bounds = self.extract_salary_bounds(text)
        if bounds is None:
            return True

        _, max_salary = bounds
        if max_salary < self.min_salary_threshold:
            log.info("Job %s (%s) filtered: max salary $%.0f below threshold $%.0f", job.id, job.company, max_salary, self.min_salary_threshold)
            return False

        return True
