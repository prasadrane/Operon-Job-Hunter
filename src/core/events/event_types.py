"""Domain event types for agent coordination (P5a foundation)."""
from enum import Enum


class EventType(str, Enum):
    """Events agents and integrations publish on the core domain bus."""

    # Pipeline lifecycle
    JOB_DISCOVERED = "job_discovered"
    JOB_ENRICHED = "job_enriched"
    JOB_EVALUATED = "job_evaluated"
    JOB_TAILORED = "job_tailored"
    APPLICATION_SUBMITTED = "application_submitted"
    APPLICATION_STATUS_CHANGED = "application_status_changed"
    INTERVIEW_SCHEDULED = "interview_scheduled"

    # Discovery internals
    CRAWLER_COMPLETED = "crawler_completed"
    CRAWLER_FAILED = "crawler_failed"

    # Agent meta
    AGENT_DECISION_MADE = "agent_decision_made"
    INTEGRATION_COMPLETED = "integration_completed"
