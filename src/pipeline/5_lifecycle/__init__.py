"""Stage 5: Lifecycle Monitoring, Follow-Up Cadence & Funnel Analytics."""

from .status_classifier import StatusClassifier
from .followup_engine import (
    CadenceConfig,
    DraftFollowup,
    FollowupEngine,
    FollowupItem,
    UrgencyLevel,
)
from .funnel_analytics import (
    FunnelAnalytics,
    FunnelMetrics,
)
from .healing_strategies import (
    CrawlerError,
    HealingCandidate,
    HealingResult as LegacyHealingResult,
    attempt_healing,
    validate_candidate,
)
from .self_healing_agent import (
    HealingAction,
    HealingAuditLog,
    HealingReport as LegacyHealingReport,
    SelfHealingAgent,
    detect_errors_from_logs,
    update_company_config,
)
# New multi-agent healing package
from .healing import (
    BaseHealer,
    HealingOrchestrator,
    build_default_orchestrator,
    DiscoveryHealer,
    GatewayHealer,
    EvaluationHealer,
    TailoringHealer,
    SubmissionHealer,
    LifecycleHealer,
)

__all__ = [
    "StatusClassifier",
    "CadenceConfig",
    "DraftFollowup",
    "FollowupEngine",
    "FollowupItem",
    "UrgencyLevel",
    "FunnelAnalytics",
    "FunnelMetrics",
    # Legacy self-healing (kept for backward compatibility)
    "CrawlerError",
    "HealingCandidate",
    "LegacyHealingResult",
    "attempt_healing",
    "validate_candidate",
    "HealingAction",
    "HealingAuditLog",
    "LegacyHealingReport",
    "SelfHealingAgent",
    "detect_errors_from_logs",
    "update_company_config",
    # New multi-agent healing orchestrator
    "BaseHealer",
    "HealingOrchestrator",
    "build_default_orchestrator",
    "DiscoveryHealer",
    "GatewayHealer",
    "EvaluationHealer",
    "TailoringHealer",
    "SubmissionHealer",
    "LifecycleHealer",
]
