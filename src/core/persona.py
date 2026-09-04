"""Fictional sample candidate persona.

The public repo ships ONLY this sample profile. A real owner points
PROFILE_DATA_DIR at a private directory outside the repo; nothing in
this module may reference a real person.
"""

SAMPLE_FIRST_NAME = "Alex"
SAMPLE_LAST_NAME = "Rivera"
SAMPLE_FULL_NAME = f"{SAMPLE_FIRST_NAME} {SAMPLE_LAST_NAME}"
SAMPLE_EMAIL = "alex.rivera@example.com"
SAMPLE_PHONE = "+1 (555) 014-2033"
SAMPLE_LOCATION = "Seattle, WA"
SAMPLE_CONTACT_LINE = f"{SAMPLE_LOCATION} | {SAMPLE_PHONE} | {SAMPLE_EMAIL} | github.com/alexrivera"
SAMPLE_RESUME_PDF_NAME = "Alex_Rivera_Resume.pdf"

# Core stack — mock scorer keyword overlap + demo job seeding rely on these.
SAMPLE_SKILLS = [
    "Python", "FastAPI", "Django", "PostgreSQL", "Redis", "Kafka",
    "Kubernetes", "Docker", "AWS", "Terraform", "gRPC", "CI/CD",
]

SAMPLE_PROFILE_SUMMARY = (
    "Backend/platform engineer with 6+ years building high-throughput "
    "event pipelines and API services in Python (FastAPI, Django). "
    "Track record: 40M events/day ingestion platform, payments "
    "idempotency rework, Kubernetes migration, and latency cuts "
    "measured in p95. Strong on PostgreSQL, Kafka, Redis, AWS."
)
