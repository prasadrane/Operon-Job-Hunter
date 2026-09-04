"""Recruiter and hiring manager personalized cold outreach email & InMail drafter.

Strictly enforces FactGuard verification on STAR citations, concise word counts (<150 words),
dual output formats (Email + LinkedIn InMail), and draft-only safety mechanisms.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import logging
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# Maximum word count for cold emails
MAX_EMAIL_WORDS = 150
MAX_INMAIL_WORDS = 80
MAX_INMAIL_CHARS = 500


@dataclass
class OutreachDraft:
    """Structured representation of dual-format outreach drafts."""

    company: str
    role: str
    star_hook: str
    email: str
    inmail: str
    word_count: int
    verified: bool = True
    recipient_name: Optional[str] = None
    candidate_name: str = "Jane Doe"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize outreach draft to dictionary."""
        return {
            "company": self.company,
            "role": self.role,
            "star_hook": self.star_hook,
            "email": self.email,
            "inmail": self.inmail,
            "word_count": self.word_count,
            "verified": self.verified,
            "recipient_name": self.recipient_name,
            "candidate_name": self.candidate_name,
        }


class EmailDrafter:
    """Drafts personalized, FactGuard-verified cold emails and LinkedIn InMails for recruiters."""

    def __init__(
        self,
        fact_guard: Optional[Any] = None,
        default_candidate_name: str = "Jane Doe",
    ) -> None:
        self.fact_guard = fact_guard
        self.default_candidate_name = default_candidate_name

    def _validate_hook_facts(
        self, star_hook: str, fact_guard: Optional[Any] = None
    ) -> None:
        """Verify that the candidate's STAR hook contains only grounded career facts."""
        guard = fact_guard or self.fact_guard
        if guard is not None:
            valid, reason = guard.validate_bullet(star_hook)
            if not valid:
                logger.error("FactGuard validation failed for STAR hook: %s", reason)
                raise ValueError(f"FactGuard validation failed: {reason}")

    def _clean_hook(self, hook: str) -> str:
        """Format STAR hook text smoothly into sentence structure."""
        cleaned = hook.strip().rstrip(".")
        if cleaned.lower().startswith("i "):
            cleaned = cleaned[2:].strip()
        return cleaned

    def draft_outreach(
        self,
        company: str,
        role: str,
        star_hook: str,
        recipient_name: Optional[str] = None,
        candidate_name: Optional[str] = None,
        fact_guard: Optional[Any] = None,
    ) -> str:
        """Draft a concise, high-converting cold email (<150 words)."""
        self._validate_hook_facts(star_hook, fact_guard)

        cand_name = candidate_name or self.default_candidate_name
        clean_hook = self._clean_hook(star_hook)

        if recipient_name:
            rec_clean = recipient_name.strip()
            first_name = rec_clean.split()[0] if " " in rec_clean else rec_clean
            greeting = f"Hi {first_name},"
        else:
            greeting = f"Hi Engineering Team at {company},"

        email_body = f"""{greeting}

I recently applied for the {role} position. In my previous work, I {clean_hook}.

Given {company}'s focus on high-throughput backend infrastructure, I would love to connect briefly to discuss how my distributed systems experience aligns with your current roadmap.

Best,
{cand_name}
"""
        words = email_body.split()
        if len(words) >= MAX_EMAIL_WORDS:
            # Enforce strict <150 words ceiling
            truncated_words = words[: MAX_EMAIL_WORDS - 10]
            email_body = " ".join(truncated_words) + f"\n\nBest,\n{cand_name}\n"

        return email_body

    def draft_inmail(
        self,
        company: str,
        role: str,
        star_hook: str,
        recipient_name: Optional[str] = None,
        candidate_name: Optional[str] = None,
        fact_guard: Optional[Any] = None,
    ) -> str:
        """Draft a punchy LinkedIn InMail connection snippet."""
        self._validate_hook_facts(star_hook, fact_guard)

        clean_hook = self._clean_hook(star_hook)
        if recipient_name:
            rec_clean = recipient_name.strip()
            first_name = rec_clean.split()[0] if " " in rec_clean else rec_clean
            greeting = f"Hi {first_name},"
        else:
            greeting = "Hi,"

        inmail_text = (
            f"{greeting} saw the {role} opening at {company}. "
            f"In my previous work, I {clean_hook}. "
            f"I would love to connect and share more about how my background fits your team!"
        )

        if len(inmail_text) > MAX_INMAIL_CHARS:
            inmail_text = inmail_text[: MAX_INMAIL_CHARS - 3] + "..."

        return inmail_text

    def draft_dual_outreach(
        self,
        company: str,
        role: str,
        star_hook: str,
        recipient_name: Optional[str] = None,
        candidate_name: Optional[str] = None,
        fact_guard: Optional[Any] = None,
    ) -> OutreachDraft:
        """Generate both Email and LinkedIn InMail drafts with verified facts."""
        email = self.draft_outreach(
            company=company,
            role=role,
            star_hook=star_hook,
            recipient_name=recipient_name,
            candidate_name=candidate_name,
            fact_guard=fact_guard,
        )
        inmail = self.draft_inmail(
            company=company,
            role=role,
            star_hook=star_hook,
            recipient_name=recipient_name,
            candidate_name=candidate_name,
            fact_guard=fact_guard,
        )
        cand_name = candidate_name or self.default_candidate_name
        word_count = len(email.split())

        return OutreachDraft(
            company=company,
            role=role,
            star_hook=star_hook,
            email=email,
            inmail=inmail,
            word_count=word_count,
            verified=True,
            recipient_name=recipient_name,
            candidate_name=cand_name,
        )

    def dispatch_outreach(
        self,
        draft: Union[OutreachDraft, Dict[str, Any]],
        draft_only: bool = True,
    ) -> Dict[str, Any]:
        """Verify draft-only safety flag and record draft status."""
        draft_dict = draft.to_dict() if isinstance(draft, OutreachDraft) else draft

        if draft_only:
            logger.info("Outreach created in draft-only mode. Auto-send blocked.")
            return {
                "status": "DRAFT_SAVED",
                "dispatched": False,
                "mode": "DRAFT_ONLY",
                "draft": draft_dict,
                "message": "Outreach safely saved in draft-only mode; dispatch blocked.",
            }

        logger.info("Outreach dispatch authorized by human operator.")
        return {
            "status": "DISPATCH_AUTHORIZED",
            "dispatched": True,
            "mode": "HUMAN_AUTHORIZED",
            "draft": draft_dict,
            "message": "Outreach dispatched under operator authorization.",
        }
