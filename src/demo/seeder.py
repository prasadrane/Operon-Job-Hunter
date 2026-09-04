"""Deterministic demo data for the offline portfolio demo.

All companies, jobs, and the candidate are fictional (see src/core/persona.py).
"""
from typing import Dict, List, Optional

from src.core.config import get_settings
from src.core.db.repository import JobRepository
from src.core.models import JobPosting
from src.core.persona import (
    SAMPLE_EMAIL,
    SAMPLE_FIRST_NAME,
    SAMPLE_FULL_NAME,
    SAMPLE_LAST_NAME,
    SAMPLE_PHONE,
    SAMPLE_PROFILE_SUMMARY,
    SAMPLE_SKILLS,
)

DEMO_JOB_COUNT = 20

_STRONG_STACK = (
    "We run Python 3.12, FastAPI, Kafka, PostgreSQL, Redis on Kubernetes in AWS. "
    "You will design event-driven services, own p95 latency budgets, and drive "
    "Terraform-based infra. Expect contract testing, gRPC between services, and "
    "on-call ownership of what you build."
)
_MID_STACK = (
    "Backend role focused on Go and Java services with PostgreSQL and gRPC. "
    "Some Python tooling. Kubernetes in production, AWS hosting, CI/CD pipelines, "
    "message queues (SQS/RabbitMQ), observability via Grafana."
)
_WEAK_STACK = (
    "Frontend-heavy role: React, TypeScript, CSS design systems, accessibility "
    "audits, Storybook, browser performance profiling. Backend exposure minimal. "
    "You will collaborate with product designers, maintain reusable UI component libraries, "
    "build responsive user experiences, and optimize web vitals across desktop and mobile devices."
)
_GHOST_SHAPE = (
    "Rockstar ninja wanted for many openings across multiple teams. Must know "
    "every technology. Competitive salary range TBD. Apply now, immediate start, "
    "multiple positions available, reposted several times."
)


def _job(
    n: int,
    company: str,
    title: str,
    desc: str,
    portal: str = "generic",
    url: Optional[str] = None,
    seniority: str = "senior",
) -> JobPosting:
    jid = f"demo_{n:03d}"
    return JobPosting(
        id=jid,
        company=company,
        title=title,
        url=url or f"https://{company.lower().replace(' ', '-')}.example.com/jobs/{jid}",
        portal_type=portal,
        source="demo",
        location="Remote - US",
        description=desc,
        seniority=seniority,
    )


def _build_jobs() -> List[JobPosting]:
    jobs = [
        # 8 strong fits (Alex's stack front and center)
        _job(1, "Vertexa", "Senior Backend Engineer - Ingestion", _STRONG_STACK),
        _job(2, "Cloudhaven", "Staff Platform Engineer", _STRONG_STACK + " Bonus: Kafka consumer rebalancing and backpressure experience."),
        _job(3, "Datawheel", "Senior Python Engineer", _STRONG_STACK),
        _job(4, "Orbital Systems", "Backend Engineer - Realtime", _STRONG_STACK),
        _job(5, "Pinehurst Robotics", "Senior Software Engineer, Backend", _STRONG_STACK),
        _job(6, "Vertexa", "Platform Engineer - Kubernetes", _STRONG_STACK + " Terraform modules ownership."),
        _job(7, "Northbeam Data", "Senior Backend Engineer", _STRONG_STACK),
        _job(8, "Cloudhaven", "Backend Engineer - Payments", _STRONG_STACK + " Idempotency and exactly-once processing experience valued."),
        # 6 mid fits (adjacent stacks)
        _job(9, "Datawheel", "Backend Engineer II", _MID_STACK, seniority="mid"),
        _job(10, "Stellar Freight", "Software Engineer, Services", _MID_STACK, seniority="mid"),
        _job(11, "Orbital Systems", "Backend Engineer (Go)", _MID_STACK, seniority="mid"),
        _job(12, "Bluepeak Health", "Application Engineer", _MID_STACK, seniority="mid"),
        _job(13, "Pinehurst Robotics", "Software Engineer, Infra", _MID_STACK, seniority="mid"),
        _job(14, "Vertexa", "Junior Backend Engineer", _MID_STACK, seniority="junior"),
        # 3 weak fits (frontend mismatch)
        _job(15, "Bright UI Co", "Senior Frontend Engineer", _WEAK_STACK),
        _job(16, "Pixelwave", "UI Engineer", _WEAK_STACK),
        _job(17, "Datawheel", "Data Scientist", "Modeling focus: scikit-learn, notebooks, stakeholder storytelling, dashboards, A/B testing. Little production backend work. Requires statistical modeling, experimentation analysis, metrics design, and cross-functional reporting with product managers."),
        # 3 ghost-shaped postings
        _job(18, "Shadowcorp", "Software Engineer (Multiple Openings)", _GHOST_SHAPE),
        _job(19, "InstantHire LLC", "Ninja Developer - Immediate Start", _GHOST_SHAPE),
        _job(20, "GhostWorks", "Full Stack Rockstar", _GHOST_SHAPE),
    ]
    # Two strong fits become mock-ATS submission targets at demo time.
    jobs[0] = jobs[0].model_copy(update={"portal_type": "greenhouse"})
    jobs[1] = jobs[1].model_copy(update={"portal_type": "lever"})
    return jobs


def seed_demo(db_path: str, ats_base_url: Optional[str] = None) -> List[JobPosting]:
    """Seed fictional demo jobs + sample profile into the given DB."""
    repo = JobRepository(db_path)
    profile: Dict = {
        "candidate_id": getattr(get_settings(), "active_candidate_id", "demo-candidate"),
        "name": SAMPLE_FULL_NAME,
        "first_name": SAMPLE_FIRST_NAME,
        "last_name": SAMPLE_LAST_NAME,
        "email": SAMPLE_EMAIL,
        "phone": SAMPLE_PHONE,
        "summary": SAMPLE_PROFILE_SUMMARY,
        "skills": SAMPLE_SKILLS,
    }
    repo.save_profile(profile)

    jobs = _build_jobs()
    if ats_base_url:
        by_portal = [j for j in jobs if j.portal_type in {"greenhouse", "lever"}]
        gh = next(j for j in by_portal if j.portal_type == "greenhouse")
        lever = next(j for j in by_portal if j.portal_type == "lever")
        gh = gh.model_copy(update={"url": f"{ats_base_url}/greenhouse/test_job"})
        lever = lever.model_copy(update={"url": f"{ats_base_url}/lever/test_job"})
        jobs = [gh if j.id == gh.id else lever if j.id == lever.id else j for j in jobs]

    for job in jobs:
        repo.insert_job(job)
    return jobs
