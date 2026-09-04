"""Core Pydantic models and data schemas for CareerGraph AI."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class JobStatus(str, Enum):
    """Lifecycle stages and statuses for a job posting."""

    DISCOVERED = "discovered"
    EVALUATING = "evaluating"
    MATCHED = "matched"
    TAILORING = "tailoring"
    TAILORED = "tailored"
    SUBMITTING = "submitting"
    APPLIED = "applied"
    ACKNOWLEDGED = "acknowledged"
    ASSESSMENT = "assessment"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOST_JOB = "ghost_job"
    IGNORED = "ignored"
    FAILED = "failed"


class JobPosting(BaseModel):
    """Standardized representation of a discovered job posting."""

    id: str
    company: str
    title: str
    url: str
    portal_type: str = "generic"
    source: str = "scanner"
    status: JobStatus = JobStatus.DISCOVERED
    location: Optional[str] = None
    description: Optional[str] = None
    h1b_sponsored: Optional[bool] = None
    posted_at: Optional[datetime] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    raw_data: Optional[Dict[str, Any]] = None

    # Enriched metadata for UI Kanban & evaluation displays
    fit_score: Optional[float] = None
    matched_skills: Optional[List[str]] = Field(default_factory=list)
    missing_skills: Optional[List[str]] = Field(default_factory=list)
    tech_stack: Optional[List[str]] = Field(default_factory=list)
    salary_range: Optional[str] = None
    seniority: Optional[str] = None
    is_ghost_job: Optional[bool] = None
    work_auth_blocker: Optional[bool] = None
    evaluation_reason: Optional[str] = None
    skill_match_score: Optional[float] = None


class EvaluationResult(BaseModel):
    """Result of Stage 2 (7-Block Evaluation & Ghost-Job Guard)."""

    id: Optional[str] = None
    job_id: Optional[str] = None
    fit_score: float = 0.0
    score: Optional[float] = None
    reason: Optional[str] = None
    block_scores: Dict[str, Any] = Field(default_factory=dict)
    work_auth_blocker: bool = False
    is_ghost_job: bool = False
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def sync_scores(self) -> "EvaluationResult":
        """Synchronize score and fit_score if one is provided."""
        if self.score is not None and self.fit_score == 0.0:
            self.fit_score = float(self.score)
        elif self.fit_score != 0.0 and self.score is None:
            self.score = self.fit_score
        return self


class TailoredArtifacts(BaseModel):
    """Artifacts produced by Stage 3 (GraphRAG Tailoring & PDF Generation)."""

    id: Optional[str] = None
    job_id: Optional[str] = None
    resume_pdf_path: Optional[str] = None
    resume_json_path: Optional[str] = None
    cover_letter_path: Optional[str] = None
    qa_answers: Dict[str, Any] = Field(default_factory=dict)
    linkedin_outreach: Optional[str] = None
    tailored_at: datetime = Field(default_factory=datetime.utcnow)


class SubmissionReceipt(BaseModel):
    """Receipt and audit trail produced by Stage 4 (Playwright Submitter)."""

    id: Optional[str] = None
    job_id: Optional[str] = None
    success: bool = False
    confirmation_id: Optional[str] = None
    screenshot_path: Optional[str] = None
    portal_type: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None


class ApplicationRecord(BaseModel):
    """Application lifecycle tracker for Stage 5 (Lifecycle Monitoring & Follow-Up)."""

    id: Optional[str] = None
    job_id: str
    company: str
    title: str
    status: JobStatus = JobStatus.APPLIED
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    portal_url: Optional[str] = None
    resume_pdf_path: Optional[str] = None
    submission_receipt_id: Optional[str] = None
    followup_due_date: Optional[datetime] = None
    last_status_update: Optional[datetime] = None
    notes: Optional[str] = None


from src.core.persona import (
    SAMPLE_EMAIL,
    SAMPLE_FIRST_NAME,
    SAMPLE_LAST_NAME,
    SAMPLE_PHONE,
)


class CandidateProfile(BaseModel):
    """Unified candidate profile and applicant details for auto-submission."""

    first_name: str = SAMPLE_FIRST_NAME
    last_name: str = SAMPLE_LAST_NAME
    full_name: str = ""
    email: str = SAMPLE_EMAIL
    phone: str = SAMPLE_PHONE
    location: str = "Seattle, WA"
    address: str = "123 Pine St"
    city: str = "Seattle"
    state: str = "WA"
    zip_code: str = "98101"
    linkedin: str = "https://linkedin.com/in/alex-rivera"
    github: str = "https://github.com/alexrivera"
    portfolio: str = "https://alexrivera.dev"
    website: str = "https://alexrivera.dev"
    password: str = "SecurePass123!"
    us_work_authorized: bool = True
    requires_sponsorship: bool = True
    veteran_status: str = "Decline to Self-Identify"
    disability_status: str = "I Do Not Wish To Answer"
    gender: str = "Decline to Self-Identify"
    race_ethnicity: str = "Decline to Self-Identify"
    custom_fields: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def populate_full_name(self) -> "CandidateProfile":
        if not self.full_name:
            self.full_name = f"{self.first_name} {self.last_name}".strip()
        return self


class WorkdayAccountProfile(BaseModel):
    """Dedicated Workday Enterprise Multi-Step application autofill profile."""

    email: str = SAMPLE_EMAIL
    password: str = "CareerGraph#2026Secure!"
    first_name: str = SAMPLE_FIRST_NAME
    last_name: str = SAMPLE_LAST_NAME
    phone: str = SAMPLE_PHONE
    phone_device_type: str = "Mobile"
    address_line1: str = "123 Pine St"
    city: str = "Seattle"
    state: str = "WA"
    postal_code: str = "98101"
    country: str = "United States of America"
    is_authorized_us: bool = True
    needs_sponsorship_future: bool = True
    previously_employed: bool = False
    veteran_status: str = "not_veteran"
    disability_status: str = "no_disability"
    gender: str = "Male"
    race_ethnicity: str = "Asian"
    source_heard_about: str = "LinkedIn"
    updated_at: datetime = Field(default_factory=datetime.utcnow)


