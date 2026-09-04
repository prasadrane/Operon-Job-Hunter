"""PipelineGraphState definition for LangGraph orchestrator with typed severity and monotonic reducers."""
import operator
from enum import IntEnum
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class SeverityLevel(IntEnum):
    """Monotonic severity levels for pipeline validation gating.

    Ordering: CLEAN < WARNING < CRITICAL_RETRY < FATAL_BLOCK.
    Reducers only allow escalation — never downgrade.
    """

    CLEAN = 0
    WARNING = 1
    CRITICAL_RETRY = 2
    FATAL_BLOCK = 3


# ── Reducers for LangGraph operator-annotated state fields ────────────────────

def hard_blocks_reducer(current: Optional[List[str]], new: Optional[List[str]]) -> List[str]:
    """Monotonic reducer: accumulates hard blocks, never removes them.

    Hard blocks are fatal pipeline blockers (e.g. work_auth, h1b_denied).
    Once added, they persist for the entire pipeline run.
    """
    cur = list(current) if current else []
    additions = list(new) if new else []
    seen = set(cur)
    for item in additions:
        if item not in seen:
            cur.append(item)
            seen.add(item)
    return cur


def soft_flags_reducer(current: Optional[List[str]], new: Optional[List[str]]) -> List[str]:
    """Accumulator for soft flags (warnings that don't block but signal caution).

    Soft flags can be overridden by downstream context but are never silently dropped.
    """
    cur = list(current) if current else []
    additions = list(new) if new else []
    seen = set(cur)
    for item in additions:
        if item not in seen:
            cur.append(item)
            seen.add(item)
    return cur


def validation_level_reducer(
    current: Optional[SeverityLevel], new: Optional[SeverityLevel]
) -> Optional[SeverityLevel]:
    """Monotonic reducer: validation_level only escalates, never downgrades.

    If current is None (initial), takes the new value.
    """
    if current is None:
        return new
    if new is None:
        return current
    return max(current, new)


class PipelineGraphState(TypedDict, total=False):
    """LangGraph state schema for job application pipeline with accumulators and reducers."""

    job_id: str
    company: str
    title: str
    url: str
    portal_type: str
    fit_score: float
    current_stage: str
    is_ghost_job: bool
    work_auth_blocker: bool
    evaluation_warning: bool
    resume_pdf_path: Optional[str]
    cover_letter_path: Optional[str]
    candidate_profile: Optional[Dict[str, Any]]
    tailored_artifacts: Optional[Dict[str, Any]]
    # ── Credential reference (NOT the credentials themselves) ─────────────
    # Key to look up in CredentialVault at runtime (e.g. "greenhouse", "lever").
    # Never store actual username/password in state — vault is queried on demand.
    credential_ref: Optional[str]
    submission_receipt_id: Optional[str]
    submission_screenshot_path: Optional[str]
    screenshot_path: Optional[str]
    telegram_message_id: Optional[int]
    qa_answers: Annotated[Dict[str, str], operator.ior]
    audit_logs: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[str], operator.add]
    evaluator_critiques: Annotated[List[Dict[str, Any]], operator.add]
    # ── P5a: agent coordination (append-only via operator.add; JSON-safe dicts) ─
    agent_decisions: Annotated[List[Dict[str, Any]], operator.add]
    integration_results: Annotated[List[Dict[str, Any]], operator.add]
    # ── v2: typed severity + monotonic blockers ──────────────────────────────
    hard_blocks: Annotated[List[str], hard_blocks_reducer]
    soft_flags: Annotated[List[str], soft_flags_reducer]
    validation_level: SeverityLevel
    provenance_metadata: Dict[str, Any]


TRANSIENT_STATE_KEYS = {
    "raw_dom_snapshot",
    "transient_base64_image",
    "dom_tree",
    "page_source",
    "raw_html",
    "raw_screenshot",
}


def prune_transient_state(state: PipelineGraphState) -> PipelineGraphState:
    """Prune temporary/transient visual and DOM blobs from state to keep checkpoints under 10KB.

    Retains all core metadata, file paths, Q&A maps, and compacts oversized audit logs.
    """
    pruned: Dict[str, Any] = {}
    for key, value in state.items():
        if key in TRANSIENT_STATE_KEYS:
            continue
        if key == "audit_logs" and isinstance(value, list) and len(value) > 25:
            # Keep most recent 25 log entries to prevent unbound state bloat
            pruned[key] = value[-25:]
        elif key == "errors" and isinstance(value, list) and len(value) > 10:
            pruned[key] = value[-10:]
        elif key == "agent_decisions" and isinstance(value, list) and len(value) > 50:
            pruned[key] = value[-50:]
        else:
            pruned[key] = value

    return PipelineGraphState(**pruned)
