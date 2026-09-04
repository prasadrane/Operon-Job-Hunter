"""Personalized LinkedIn connection note & outreach drafter.

Strictly adheres to LinkedIn's <= 300 character connection request limit.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.core.models import JobPosting

logger = logging.getLogger(__name__)

MAX_OUTREACH_CHARS = 300


class OutreachDrafter:
    """Drafts concise, high-converting LinkedIn outreach notes for recruiters and hiring managers."""

    def __init__(self, retriever: Optional[Any] = None) -> None:
        self.retriever = retriever

    def _truncate_if_needed(self, text: str) -> str:
        """Enforce strict 300-character ceiling."""
        if len(text) <= MAX_OUTREACH_CHARS:
            return text
        return text[:MAX_OUTREACH_CHARS - 3] + "..."

    def draft_recruiter_dm(self, job: JobPosting, recruiter_name: Optional[str] = None) -> str:
        """Generate tailored note for recruiter (<=300 chars)."""
        greeting = f"Hi {recruiter_name.strip()}," if recruiter_name else "Hi,"
        company = job.company.strip() if job.company else "your team"
        title = job.title.strip() if job.title else "the open role"

        # Check for grounded causal proof hook from GraphRetriever
        proof_hook = "10+ yrs in C#/.NET, AWS microservices, and Kafka streaming at Rocket Mortgage"
        if self.retriever and hasattr(self.retriever, "retrieve_causal_paths"):
            tokens = [w for w in f"{job.title} {job.description or ''}".split() if len(w) >= 3]
            paths = self.retriever.retrieve_causal_paths(tokens[:10], max_paths=1)
            if paths:
                p = paths[0]
                tech_label = p.get("tech", ["AWS/.NET"])[0] if p.get("tech") else "AWS/.NET"
                metric_label = p.get("metric", ["high reliability"])[0] if p.get("metric") else "high reliability"
                proof_hook = f"scaled {tech_label} systems at Rocket Mortgage ({metric_label})"

        # Construct note
        note = (
            f"{greeting} I saw the {title} role at {company} and wanted to reach out. "
            f"I have {proof_hook}. "
            f"I'd love to connect and discuss how I can contribute!"
        )

        note = self._truncate_if_needed(note)
        return note

    def draft_hiring_manager_dm(self, job: JobPosting, manager_name: Optional[str] = None) -> str:
        """Generate tailored note for engineering leader/hiring manager (<=300 chars)."""
        greeting = f"Hi {manager_name.strip()}," if manager_name else "Hi,"
        company = job.company.strip() if job.company else "your team"
        title = job.title.strip() if job.title else "Senior Engineer"

        proof_hook = "high-throughput cloud systems (.NET 8, AWS ECS, Kafka) cutting costs 40%"
        if self.retriever and hasattr(self.retriever, "retrieve_causal_paths"):
            tokens = [w for w in f"{job.title} {job.description or ''}".split() if len(w) >= 3]
            paths = self.retriever.retrieve_causal_paths(tokens[:10], max_paths=1)
            if paths:
                p = paths[0]
                tech_label = p.get("tech", ["AWS/.NET"])[0] if p.get("tech") else "AWS/.NET"
                metric_label = p.get("metric", ["high reliability"])[0] if p.get("metric") else "high reliability"
                proof_hook = f"{tech_label} systems at Rocket Mortgage ({metric_label})"

        note = (
            f"{greeting} impressed by {company}'s tech. "
            f"I have 10+ yrs building {proof_hook}. "
            f"Applied for {title}—would love to connect!"
        )

        note = self._truncate_if_needed(note)
        return note

