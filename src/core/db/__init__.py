"""Database module for CareerGraph AI."""

from src.core.db.schema import init_db, migrate_schema
from src.core.db.repository import (
    JobRepository,
    EvaluationRepository,
    ArtifactRepository,
    ApplicationRepository,
)
from src.core.db.error_log import (
    ErrorEvent,
    ErrorLogRepository,
    log_error,
)
from src.core.db.provenance_logger import ProvenanceLogger

__all__ = [
    "init_db",
    "migrate_schema",
    "JobRepository",
    "EvaluationRepository",
    "ArtifactRepository",
    "ApplicationRepository",
    # Error logging
    "ErrorEvent",
    "ErrorLogRepository",
    "log_error",
    # Provenance
    "ProvenanceLogger",
]
