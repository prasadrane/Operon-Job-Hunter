"""Capability descriptors over the existing pipeline stage nodes (P5a).

Agents (P5c) introspect stages through this module instead of importing
numbered stage packages (which are not importable by dotted path from
outside — see P5a plan 'Reality check'). run_stage() is a thin, honest
dispatcher: it resolves the same node functions the LangGraph graph
uses, so behavior, telemetry and circuit-breaker wrapping stay single-
sourced. config overrides are NOT accepted: the underlying engines do
not expose them yet (tracked as tech debt).
"""
import importlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

STATE_MACHINE_MODULE = "src.pipeline.state_machine"


@dataclass(frozen=True)
class StageCapability:
    name: str
    input_requirements: List[str] = field(default_factory=list)
    output_produces: List[str] = field(default_factory=list)
    configurable_params: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "input_requirements": list(self.input_requirements),
            "output_produces": list(self.output_produces),
            "configurable_params": list(self.configurable_params),
        }


@dataclass(frozen=True)
class StageDescriptor:
    capability: StageCapability
    node_symbol: str  # attribute name on src.pipeline.state_machine


_STAGES: Dict[str, StageDescriptor] = {
    "evaluation": StageDescriptor(
        node_symbol="node_discover_and_evaluate",
        capability=StageCapability(
            name="evaluation",
            input_requirements=["job_id", "url", "company", "title"],
            output_produces=["fit_score", "is_ghost_job", "work_auth_blocker",
                             "evaluation_warning", "current_stage", "agent_decisions"],
        ),
    ),
    "tailoring": StageDescriptor(
        node_symbol="node_graphrag_tailor",
        capability=StageCapability(
            name="tailoring",
            input_requirements=["job_id"],
            output_produces=["resume_pdf_path", "cover_letter_path",
                             "tailored_artifacts", "current_stage", "agent_decisions"],
        ),
    ),
    "submission": StageDescriptor(
        node_symbol="node_submit_and_verify",
        capability=StageCapability(
            name="submission",
            input_requirements=["job_id", "resume_pdf_path"],
            output_produces=["submission_receipt_id", "submission_screenshot_path",
                             "current_stage", "agent_decisions"],
        ),
    ),
}


def get_capability(name: str) -> StageCapability:
    if name not in _STAGES:
        raise KeyError(f"Unknown stage '{name}'. Available: {sorted(_STAGES)}")
    return _STAGES[name].capability


def list_capabilities() -> List[StageCapability]:
    return [d.capability for d in _STAGES.values()]


def can_handle(name: str, state: Dict[str, Any]) -> bool:
    cap = get_capability(name)
    return all(state.get(req) is not None for req in cap.input_requirements)


def run_stage(name: str, state: Dict[str, Any]) -> Dict[str, Any]:
    if name not in _STAGES:
        raise KeyError(f"Unknown stage '{name}'. Available: {sorted(_STAGES)}")
    mod = importlib.import_module(STATE_MACHINE_MODULE)
    node: Callable[[Dict[str, Any]], Dict[str, Any]] = getattr(mod, _STAGES[name].node_symbol)
    return node(state)
