"""Pydantic models for structured resume and tailoring data."""

from typing import List, Optional
from pydantic import BaseModel, Field


class JobEntry(BaseModel):
    """Pydantic model representing a single job role or project entry."""

    heading: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    dates: str = ""
    bullets: List[str] = Field(default_factory=list)
    bullet_stories: List[str] = Field(default_factory=list)


class ResumeData(BaseModel):
    """Pydantic model representing the complete structured resume data."""

    name: str = ""
    title: str = ""
    contact_location: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    contact_linkedin: str = ""
    contact_github: str = ""
    contact_portfolio: str = ""
    summary: str = ""
    jobs: List[JobEntry] = Field(default_factory=list)
    projects: List[JobEntry] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
