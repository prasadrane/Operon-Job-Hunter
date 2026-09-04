"""Fast skill-based scoring for discovery-stage filtering. No LLM, no graph.

Matches job descriptions against candidate's core tech stack from MASTER_RESUME.md
using weighted keyword affinity. Designed for high-throughput filtering of thousands
of jobs during scan_all without LLM cost.
"""

import logging
import os
import re
from typing import Dict, List, Optional, Set

from src.core.models import JobPosting

log = logging.getLogger(__name__)


# Candidate's core skills from MASTER_RESUME.md — organized by signal weight
# High-signal: distinctive skills that strongly indicate role alignment
HIGH_SIGNAL_TECH: Set[str] = {
    "c#", ".net", ".net core", ".net 8", ".net 9", "asp.net", "asp.net core",
    "aws", "ecs", "ecs fargate", "fargate", "lambda", "dynamodb",
    "angular", "angular 12", "angular 18",
    "bedrock", "amazon bedrock", "claude", "claude sonnet",
    "kafka", "msk", "amazon msk",
    "sqs", "sns",
}

# Medium-signal: relevant but less distinctive
MEDIUM_SIGNAL_TECH: Set[str] = {
    "python", "typescript", "fastapi",
    "microservices", "distributed systems", "event-driven", "event driven",
    "docker", "kubernetes", "terraform",
    "graphql", "cqrs", "oauth2", "jwt",
    "cloudwatch", "splunk", "dynatrace", "opentelemetry",
    "ngrx", "rxjs",
    "sql server", "postgresql", "mysql",
    "lancedb", "graphrag",
    "playwright", "xunit", "tdd",
    "github actions", "circleci",
    "s3", "iam",
}

# Low-signal: generic but still relevant
LOW_SIGNAL_TECH: Set[str] = {
    "rest", "restful", "rest api", "sql", "linux", "redis",
    "elasticsearch", "grpc", "ci/cd", "clean architecture",
    "prompts", "prompt engineering",
}

# Combined index for fast lookup
_ALL_CANDIDATE_TECH: Set[str] = HIGH_SIGNAL_TECH | MEDIUM_SIGNAL_TECH | LOW_SIGNAL_TECH

# Pre-compiled regex patterns for each tech term (case-insensitive)
# For terms with non-word chars (#, .), use softer boundary to avoid \b failures
_COMPILED_PATTERNS: List[tuple] = []
for _tech in _ALL_CANDIDATE_TECH:
    escaped = re.escape(_tech)
    # If term starts/ends with non-word char, don't use \b on that side
    starts_word = _tech[0].isalnum()
    ends_word = _tech[-1].isalnum()
    left = r"\b" if starts_word else r"(?<![a-zA-Z0-9])"
    right = r"\b" if ends_word else r"(?![a-zA-Z0-9])"
    _COMPILED_PATTERNS.append((
        _tech,
        re.compile(rf"{left}{escaped}{right}", re.IGNORECASE),
    ))


class SkillScorer:
    """Fast skill-based scoring for discovery-stage filtering.

    Scores jobs 0-100 based on weighted keyword matches against candidate's
    known tech stack. No LLM, no graph — pure regex, handles thousands of
    jobs per second.
    """

    def __init__(self, threshold: Optional[float] = None) -> None:
        env_threshold = os.environ.get("SKILL_MATCH_THRESHOLD")
        if threshold is not None:
            self.threshold = threshold
        elif env_threshold:
            try:
                self.threshold = float(env_threshold)
            except ValueError:
                self.threshold = 30.0
        else:
            self.threshold = 30.0

    def score_job(self, job: JobPosting) -> float:
        """Return 0-100 skill match score. Fast: regex only, no LLM.

        Scoring:
          - Each HIGH_SIGNAL match: +20
          - Each MEDIUM_SIGNAL match: +10
          - Each LOW_SIGNAL match: +5
          - Capped at 100
        """
        text = f"{job.title or ''} {job.description or ''}"
        if not text.strip():
            return 0.0

        score = 0.0
        matched: List[str] = []

        for tech, pattern in _COMPILED_PATTERNS:
            if pattern.search(text):
                if tech in HIGH_SIGNAL_TECH:
                    score += 20
                elif tech in MEDIUM_SIGNAL_TECH:
                    score += 10
                elif tech in LOW_SIGNAL_TECH:
                    score += 5
                matched.append(tech)

        return min(score, 100.0)

    def extract_tech_tokens(self, job: JobPosting) -> List[str]:
        """Extract all matched tech tokens from a job posting (for auto-discover / logging)."""
        text = f"{job.title or ''} {job.description or ''}"
        if not text.strip():
            return []
        return [tech for tech, pattern in _COMPILED_PATTERNS if pattern.search(text)]

    def passes_threshold(self, job: JobPosting) -> bool:
        """Check if job meets minimum skill threshold. Sets job.skill_match_score."""
        score = self.score_job(job)
        job.skill_match_score = score
        return score >= self.threshold
