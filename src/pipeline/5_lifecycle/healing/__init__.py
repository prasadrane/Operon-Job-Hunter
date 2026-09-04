"""Multi-agent healing package — specialized healers for each pipeline stage.

Provides:
- HealingOrchestrator: coordinates all healers, dispatches errors by source
- BaseHealer: abstract base class for stage healers
- 6 specialized healers: Discovery, Gateway, Evaluation, Tailoring, Submission, Lifecycle
"""

from .base import BaseHealer, HealingReport, HealingResult
from .orchestrator import HealingOrchestrator, build_default_orchestrator
from .discovery_healer import DiscoveryHealer
from .gateway_healer import GatewayHealer
from .evaluation_healer import EvaluationHealer
from .tailoring_healer import TailoringHealer
from .submission_healer import SubmissionHealer
from .lifecycle_healer import LifecycleHealer

__all__ = [
    "BaseHealer",
    "HealingReport",
    "HealingResult",
    "HealingOrchestrator",
    "build_default_orchestrator",
    "DiscoveryHealer",
    "GatewayHealer",
    "EvaluationHealer",
    "TailoringHealer",
    "SubmissionHealer",
    "LifecycleHealer",
]
