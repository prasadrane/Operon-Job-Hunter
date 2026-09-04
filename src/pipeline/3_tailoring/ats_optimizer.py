"""ATS Keyword Density Optimizer: Analyzes and tunes keyword density for 75-85% ATS sweet spot."""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Set

from .career_graph_builder import TECH_TAXONOMY

logger = logging.getLogger(__name__)


@dataclass
class ATSDensityReport:
    coverage_ratio: float
    matched_keywords: List[str] = field(default_factory=list)
    missing_keywords: List[str] = field(default_factory=list)
    is_in_sweet_spot: bool = False
    recommendations: List[str] = field(default_factory=list)


class ATSOptimizer:
    """Analyzes keyword overlap between Job Descriptions and tailored resumes to ensure optimal ATS ranking."""

    def __init__(self, target_min_ratio: float = 0.65, target_max_ratio: float = 0.90) -> None:
        self.target_min_ratio = target_min_ratio
        self.target_max_ratio = target_max_ratio

    def extract_requirements(self, jd_text: str) -> List[str]:
        """Extract explicit technical skills, cloud tools, and architectural concepts from JD."""
        found_reqs: List[str] = []
        jd_lower = (jd_text or "").lower()

        # 1. Match from technology taxonomy
        for tech in TECH_TAXONOMY:
            tech_clean = tech.strip()
            pattern = rf"\b{re.escape(tech_clean.lower())}\b"
            if re.search(pattern, jd_lower):
                if tech_clean not in found_reqs:
                    found_reqs.append(tech_clean)

        # 2. Match broader engineering concepts
        concepts = [
            "Microservices", "RESTful", "CI/CD", "Observability",
            "Distributed Systems", "Event-Driven", "High-Throughput",
            "Concurrency", "TDD", "Single-Table Design",
        ]
        for c in concepts:
            if re.search(rf"\b{re.escape(c.lower())}\b", jd_lower):
                if c not in found_reqs:
                    found_reqs.append(c)

        return found_reqs

    def analyze_density(
        self,
        resume_text: str,
        jd_text: str,
    ) -> ATSDensityReport:
        """Calculate keyword coverage ratio and generate optimization recommendations."""
        reqs = self.extract_requirements(jd_text)
        if not reqs:
            return ATSDensityReport(
                coverage_ratio=1.0,
                matched_keywords=[],
                missing_keywords=[],
                is_in_sweet_spot=True,
                recommendations=["No specific technical requirements extracted from JD."],
            )

        resume_lower = (resume_text or "").lower()
        matched: List[str] = []
        missing: List[str] = []

        for req in reqs:
            pattern = rf"\b{re.escape(req.lower())}\b"
            if re.search(pattern, resume_lower):
                matched.append(req)
            else:
                missing.append(req)

        coverage = len(matched) / len(reqs)
        is_sweet_spot = self.target_min_ratio <= coverage <= self.target_max_ratio

        recommendations: List[str] = []
        if coverage < self.target_min_ratio:
            recommendations.append(
                f"Keyword match ({coverage:.0%}) is below the {self.target_min_ratio:.0%} target. "
                f"Consider incorporating verified evidence for: {', '.join(missing[:4])}."
            )
        elif coverage > self.target_max_ratio:
            recommendations.append(
                f"Keyword density ({coverage:.0%}) is high. Ensure bullets remain natural and human-readable without keyword stuffing."
            )
        else:
            recommendations.append(
                f"Keyword density ({coverage:.0%}) is in the optimal ATS sweet spot ({self.target_min_ratio:.0%}-{self.target_max_ratio:.0%})."
            )

        return ATSDensityReport(
            coverage_ratio=coverage,
            matched_keywords=matched,
            missing_keywords=missing,
            is_in_sweet_spot=is_sweet_spot,
            recommendations=recommendations,
        )
