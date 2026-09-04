"""3-Persona Composite Evaluator Panel for resume draft assessment.

Evaluates resume bullets across 3 distinct personas:
- Hiring Manager (40%): Quantified impact metrics, scale, architecture depth
- ATS Scanner (35%): Keyword density, match rate, exact terminology coverage
- Recruiter (25%): Strong action verbs, brevity, readability, structure
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Weak/passive phrases to penalize in recruiter scoring
WEAK_PHRASES = [
    r"\bworked on\b",
    r"\bhelped with\b",
    r"\bhelped team\b",
    r"\bassisted with\b",
    r"\bwrote code\b",
    r"\btasks\b",
    r"\bdid\b",
    r"\bresponsible for\b",
]

# Quantified metric patterns expected by hiring managers
METRIC_PATTERNS = [
    r"\b\d+M\+?\b",
    r"\b\d+k\+?\b",
    r"\b\d+%\b",
    r"\$\d+",
    r"\b\d+x\b",
    r"\b\d+\s*ms\b",
    r"\b\d+\s*seconds?\b",
    r"\b\d+\s*users\b",
    r"\b99\.\d+%\b",
]


_METRIC_RES = [re.compile(pat, re.IGNORECASE) for pat in METRIC_PATTERNS]
_WEAK_RES = [re.compile(pat, re.IGNORECASE) for pat in WEAK_PHRASES]


class EvaluatorPanel:
    """Multi-persona composite evaluator assessing draft resume bullets."""

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        pass_threshold: float = 85.0,
    ) -> None:
        self.weights = weights or {
            "hiring_manager": 0.40,
            "ats_scanner": 0.35,
            "recruiter": 0.25,
        }
        self.pass_threshold = pass_threshold

    def _score_hiring_manager(self, bullets: List[str]) -> tuple[float, List[Dict[str, Any]]]:
        """Score for quantified business and technical impact."""
        if not bullets:
            return 0.0, []

        critiques: List[Dict[str, Any]] = []
        bullets_with_metrics = 0

        for i, b in enumerate(bullets):
            has_metric = any(pat.search(b) for pat in _METRIC_RES)
            if has_metric:
                bullets_with_metrics += 1
            else:
                critiques.append({
                    "bullet_index": i,
                    "persona": "hiring_manager",
                    "issue": "Lacks quantified impact metric, percentage, or scale",
                })

        metric_ratio = bullets_with_metrics / max(len(bullets), 1)
        # Score ranges from 60.0 (no metrics) to 95.0 (all bullets quantified)
        score = 60.0 + (metric_ratio * 35.0)
        return min(round(score, 1), 100.0), critiques

    def _score_ats_scanner(
        self, bullets: List[str], target_keywords: List[str]
    ) -> tuple[float, List[Dict[str, Any]]]:
        """Score for keyword matching against target job description."""
        if not target_keywords:
            return 95.0, []

        full_text = " ".join(bullets).lower()
        matched = []
        missing = []

        for kw in target_keywords:
            kw_clean = kw.strip().lower()
            if not kw_clean:
                continue
            # Use non-word boundaries (?<!\w) and (?!\w) to handle C#, C++, .NET
            pattern = re.compile(rf"(?<!\w){re.escape(kw_clean)}(?!\w)", re.IGNORECASE)
            if pattern.search(full_text):
                matched.append(kw)
            else:
                missing.append(kw)

        match_ratio = len(matched) / max(len(target_keywords), 1)
        critiques: List[Dict[str, Any]] = []

        if missing:
            critiques.append({
                "bullet_index": 0,
                "persona": "ats_scanner",
                "issue": f"Missing key tech keyword(s): {', '.join(missing[:3])}",
                "missing_keywords": missing,
            })

        score = 55.0 + (match_ratio * 40.0)
        return min(round(score, 1), 100.0), critiques

    def _score_recruiter(self, bullets: List[str]) -> tuple[float, List[Dict[str, Any]]]:
        """Score for readability, action verbs, and avoidance of passive phrasing."""
        if not bullets:
            return 0.0, []

        critiques: List[Dict[str, Any]] = []
        deductions = 0.0

        for i, b in enumerate(bullets):
            for pat in _WEAK_RES:
                if pat.search(b):
                    deductions += 15.0
                    critiques.append({
                        "bullet_index": i,
                        "persona": "recruiter",
                        "issue": f"Contains passive or weak phrasing: '{pat.pattern}'",
                    })

        base_score = 92.0
        score = max(base_score - deductions, 40.0)
        return min(round(score, 1), 100.0), critiques

    def evaluate_draft(
        self, bullets: List[str], target_keywords: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Evaluate resume bullets and calculate composite score across 3 personas."""
        keywords = target_keywords or []
        hm_score, hm_critiques = self._score_hiring_manager(bullets)
        ats_score, ats_critiques = self._score_ats_scanner(bullets, keywords)
        recruiter_score, recruiter_critiques = self._score_recruiter(bullets)

        composite = (
            self.weights["hiring_manager"] * hm_score
            + self.weights["ats_scanner"] * ats_score
            + self.weights["recruiter"] * recruiter_score
        )
        composite = round(composite, 2)

        all_critiques = hm_critiques + ats_critiques + recruiter_critiques
        passed = composite >= self.pass_threshold

        return {
            "composite_score": composite,
            "hm_score": hm_score,
            "ats_score": ats_score,
            "recruiter_score": recruiter_score,
            "critiques": all_critiques,
            "passed": passed,
        }
