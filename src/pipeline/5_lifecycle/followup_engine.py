"""7-Day Follow-Up Cadence Tracker & Message Generator for CareerGraph AI."""

import re
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from src.core.db.repository import ApplicationRepository
from src.core.models import ApplicationRecord, CandidateProfile, JobStatus


class UrgencyLevel(str, Enum):
    """Urgency level classification for pending follow-ups."""

    URGENT = "urgent"
    OVERDUE = "overdue"
    WAITING = "waiting"
    COLD = "cold"
    RETIRED = "retired"


class CadenceConfig(BaseModel):
    """Configurable cadence timeframes in days."""

    applied_first_days: int = 5
    applied_subsequent_days: int = 5
    applied_max_followups: int = 2
    responded_initial_days: int = 1
    responded_subsequent_days: int = 3
    interview_thankyou_days: int = 1


class FollowupItem(BaseModel):
    """Actionable follow-up item with generated drafts and urgency."""

    application_id: str
    job_id: str
    company: str
    title: str
    status: str
    applied_at: datetime
    days_since_applied: int
    followup_count: int = 0
    due_date: datetime
    days_until_due: int
    urgency: UrgencyLevel
    email_draft: Optional[str] = None
    linkedin_message: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None


class DraftFollowup(BaseModel):
    """Safety-governed follow-up draft requiring candidate review and explicit approval."""

    application_id: Optional[str] = None
    company: str
    role: str
    content: str
    is_draft: bool = True
    requires_approval: bool = True
    approved_by_candidate: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "draft_pending_approval"


class FollowupEngine:
    """Manages application follow-up schedules, urgency evaluation, and personalized outreach drafts."""

    def __init__(
        self,
        cadence_days: int = 5,
        max_followups: int = 2,
        cadence_config: Optional[CadenceConfig] = None,
        app_repo: Optional[ApplicationRepository] = None,
        candidate_profile: Optional[CandidateProfile] = None,
        brain: Optional[Any] = None,
    ):
        self.cadence_days = cadence_days
        self.max_followups = max_followups
        self.cadence_config = cadence_config or CadenceConfig(
            applied_first_days=cadence_days,
            applied_max_followups=max_followups,
        )
        self.app_repo = app_repo
        self.candidate_profile = candidate_profile or CandidateProfile()
        self._brain = brain

    @property
    def brain(self) -> Optional[Any]:
        if self._brain is None:
            from src.brain.factory import get_brain
            self._brain = get_brain()
        return self._brain

    def calculate_due_date(self, base_date: datetime, days: Optional[int] = None) -> datetime:
        """Calculate the next follow-up due date based on a starting date and cadence."""
        delta_days = days if days is not None else self.cadence_days
        return base_date + timedelta(days=delta_days)

    def compute_urgency(
        self,
        status: Union[JobStatus, str],
        days_since_app: int,
        days_since_last_followup: Optional[int] = None,
        followup_count: int = 0,
    ) -> UrgencyLevel:
        """Compute the urgency level based on status, elapsed days, and previous touches."""
        st = status.value.lower() if isinstance(status, JobStatus) else str(status).lower()

        if st in ("applied", "acknowledged", "discovered", "submitting"):
            if followup_count >= self.cadence_config.applied_max_followups:
                return UrgencyLevel.COLD
            if followup_count == 0 and days_since_app >= self.cadence_config.applied_first_days:
                return UrgencyLevel.OVERDUE
            if (
                followup_count > 0
                and days_since_last_followup is not None
                and days_since_last_followup >= self.cadence_config.applied_subsequent_days
            ):
                return UrgencyLevel.OVERDUE
            return UrgencyLevel.WAITING

        if st in ("responded", "matched"):
            if days_since_last_followup is not None:
                return (
                    UrgencyLevel.OVERDUE
                    if days_since_last_followup >= self.cadence_config.responded_subsequent_days
                    else UrgencyLevel.WAITING
                )
            if days_since_app < self.cadence_config.responded_initial_days:
                return UrgencyLevel.URGENT
            if days_since_app >= self.cadence_config.responded_subsequent_days:
                return UrgencyLevel.OVERDUE
            return UrgencyLevel.WAITING

        if st in ("interview", "interviewing", "assessment"):
            if days_since_last_followup is not None:
                return (
                    UrgencyLevel.OVERDUE
                    if days_since_last_followup >= self.cadence_config.responded_subsequent_days
                    else UrgencyLevel.WAITING
                )
            if days_since_app >= self.cadence_config.interview_thankyou_days:
                return UrgencyLevel.OVERDUE
            return UrgencyLevel.WAITING

        return UrgencyLevel.WAITING

    def extract_contacts_from_notes(self, notes: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Extract contact email and contact name from application notes."""
        if not notes:
            return None, None

        email = None
        email_match = re.search(r"[\w.-]+@[\w.-]+\.\w+", notes)
        if email_match:
            email = email_match.group(0)

        name = None
        name_match = re.search(
            r"(?:contact|recruiter|manager|with|to)\s*[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            notes,
            re.IGNORECASE,
        )
        if name_match:
            name = name_match.group(1).strip()

        return email, name

    def get_pending_followups(
        self,
        applications: Optional[List[ApplicationRecord]] = None,
        current_date: Optional[datetime] = None,
        overdue_only: bool = False,
    ) -> List[FollowupItem]:
        """Retrieve and prioritize pending follow-ups for active applications."""
        now = current_date or datetime.utcnow()

        if applications is None and self.app_repo:
            applications = self.app_repo.get_active_applications()
        elif applications is None:
            applications = []

        items: List[FollowupItem] = []
        for app in applications:
            days_since_app = max(0, (now - app.applied_at).days)
            due_date = self.calculate_due_date(app.applied_at)
            days_until_due = (due_date - now).days

            # Extract contacts
            contact_email, contact_name = self.extract_contacts_from_notes(app.notes)

            # Compute urgency
            urgency = self.compute_urgency(
                status=app.status,
                days_since_app=days_since_app,
                days_since_last_followup=None,
                followup_count=0,
            )

            # Generate drafts
            email_draft = self.generate_email_draft(
                company=app.company,
                title=app.title,
                contact_name=contact_name,
                followup_number=1,
            )
            linkedin_msg = self.generate_linkedin_message(
                company=app.company,
                title=app.title,
                contact_name=contact_name,
            )

            item = FollowupItem(
                application_id=app.id or "",
                job_id=app.job_id,
                company=app.company,
                title=app.title,
                status=app.status.value if isinstance(app.status, JobStatus) else str(app.status),
                applied_at=app.applied_at,
                days_since_applied=days_since_app,
                followup_count=0,
                due_date=due_date,
                days_until_due=days_until_due,
                urgency=urgency,
                email_draft=email_draft,
                linkedin_message=linkedin_msg,
                contact_email=contact_email,
                contact_name=contact_name,
            )

            if overdue_only:
                if urgency in (UrgencyLevel.OVERDUE, UrgencyLevel.URGENT):
                    items.append(item)
            else:
                items.append(item)

        # Sort priority: urgent -> overdue -> waiting -> cold -> retired
        urgency_priority = {
            UrgencyLevel.URGENT: 0,
            UrgencyLevel.OVERDUE: 1,
            UrgencyLevel.WAITING: 2,
            UrgencyLevel.COLD: 3,
            UrgencyLevel.RETIRED: 4,
        }
        items.sort(key=lambda x: urgency_priority.get(x.urgency, 99))
        return items

    def generate_email_draft(
        self,
        company: str,
        title: str,
        candidate_name: Optional[str] = None,
        contact_name: Optional[str] = None,
        followup_number: int = 1,
        use_brain: bool = False,
    ) -> str:
        """Generate a tailored, professional follow-up email draft."""
        cand_name = candidate_name or self.candidate_profile.full_name or "Alex Rivera"
        greeting = f"Hi {contact_name}," if contact_name else "Dear Hiring Team,"

        custom_body = None
        if use_brain and self.brain is not None:
            try:
                query = f"Draft a concise 2-sentence note expressing continued interest in the {title} role at {company}."
                res = self.brain.query(query, mode="avatar")
                if res and res.answer and len(res.answer.strip()) > 20:
                    custom_body = res.answer.strip()
            except Exception as exc:
                logger.debug("Career Brain follow-up drafting fallback: %s", exc)

        if followup_number <= 1:
            body = custom_body or (
                f"I hope this email finds you well. I am following up on my recent application for the {title} position at {company}.\n\n"
                f"I remain very enthusiastic about the opportunity to contribute to {company} and would welcome the chance to discuss how my background and engineering experience align with your team's goals.\n\n"
                f"Please let me know if you need any additional information or work samples from my end."
            )
            return (
                f"Subject: Following up on Application for {title} - {cand_name}\n\n"
                f"{greeting}\n\n"
                f"{body}\n\n"
                f"Best regards,\n"
                f"{cand_name}"
            )
        else:
            body = custom_body or (
                f"I wanted to briefly check in regarding my application for the {title} role at {company}.\n\n"
                f"I understand how busy hiring cycles can be. I am still very interested in joining {company} and would love to connect if there are any updates regarding next steps in the process.\n\n"
                f"Thank you for your time and consideration!"
            )
            return (
                f"Subject: Follow-up regarding {title} application - {cand_name}\n\n"
                f"{greeting}\n\n"
                f"{body}\n\n"
                f"Sincerely,\n"
                f"{cand_name}"
            )

    def generate_7day_followup(
        self,
        company: Optional[str] = None,
        role: Optional[str] = None,
        candidate_name: Optional[str] = None,
        app: Optional[ApplicationRecord] = None,
        contact_name: Optional[str] = None,
    ) -> str:
        """Generate a concise, professional 7-day follow-up message draft formatted for candidate review."""
        comp = company or (app.company if app else "")
        rl = role or (app.title if app else "")
        cand_name = candidate_name or self.candidate_profile.full_name or "Jane Doe"

        greeting = f"Hi {contact_name}," if contact_name else f"Hi {comp} Recruiting Team,"
        return (
            f"{greeting}\n\n"
            f"I hope you're having a great week.\n\n"
            f"I am following up on my application for the {rl} position at {comp}. "
            f"Given my background building distributed systems and high-throughput pipelines, "
            f"I remain very enthusiastic about how I can contribute to your team.\n\n"
            f"Looking forward to hearing from you.\n\n"
            f"Best regards,\n"
            f"{cand_name}"
        )

    def generate_draft_for_approval(
        self,
        company: Optional[str] = None,
        role: Optional[str] = None,
        candidate_name: Optional[str] = None,
        app: Optional[ApplicationRecord] = None,
        contact_name: Optional[str] = None,
    ) -> DraftFollowup:
        """Strictly generate a Draft-and-Approve follow-up item that cannot be sent without human confirmation."""
        comp = company or (app.company if app else "")
        rl = role or (app.title if app else "")
        app_id = app.id if app else None
        body = self.generate_7day_followup(
            company=comp,
            role=rl,
            candidate_name=candidate_name,
            app=app,
            contact_name=contact_name,
        )
        return DraftFollowup(
            application_id=app_id,
            company=comp,
            role=rl,
            content=body,
            is_draft=True,
            requires_approval=True,
            approved_by_candidate=False,
            status="draft_pending_approval",
        )

    def approve_draft(self, draft: DraftFollowup) -> DraftFollowup:
        """Approve a follow-up draft, unlocking it for candidate-approved delivery."""
        draft.approved_by_candidate = True
        draft.status = "approved"
        return draft

    def is_safe_to_send(self, draft: DraftFollowup) -> bool:
        """Safety check: strictly returns False unless draft is explicitly approved by candidate."""
        return bool(draft.approved_by_candidate and draft.status == "approved")

    def generate_linkedin_message(
        self,
        company: str,
        title: str,
        candidate_name: Optional[str] = None,
        contact_name: Optional[str] = None,
        max_chars: int = 300,
    ) -> str:
        """Generate a personalized LinkedIn follow-up connection note under 300 characters."""
        cand_first = (
            candidate_name.split()[0]
            if candidate_name
            else (self.candidate_profile.first_name or "Alex")
        )
        greeting = f"Hi {contact_name}," if contact_name else "Hello,"

        msg = (
            f"{greeting} I recently applied for the {title} role at {company} and wanted to reach out. "
            f"I'm excited about {company}'s mission and would love to connect to discuss how my background aligns with the team! - {cand_first}"
        )

        if len(msg) > max_chars:
            msg = (
                f"{greeting} I recently applied for {title} at {company}. "
                f"I'd love to connect and discuss how my skills align with your engineering goals! - {cand_first}"
            )

        return msg[:max_chars]
