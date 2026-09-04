from src.pipeline.state_schema import (
    PipelineGraphState, prune_transient_state,
)


def _decision_record(agent="a", dtype="t"):
    return {"id": "x", "agent_name": agent, "decision_type": dtype,
            "reasoning": "r", "job_id": None, "metadata": {},
            "timestamp": "2026-08-26T00:00:00+00:00"}


def test_agent_keys_present_and_dict_compatible():
    state = PipelineGraphState(job_id="j1",
                               agent_decisions=[_decision_record()],
                               integration_results=[{"integration_name": "linkedin",
                                                     "action": "search", "success": True}])
    assert state["agent_decisions"][0]["agent_name"] == "a"


def test_reducer_annotations_use_operator_add():
    # TypedDict __annotations__ carry Annotated[...] at class level
    ann = PipelineGraphState.__annotations__
    from typing import get_args
    assert "agent_decisions" in ann
    origin_args = get_args(ann["agent_decisions"])
    import operator
    assert operator.add in origin_args
    assert get_args(ann["integration_results"]) and operator.add in get_args(
        ann["integration_results"])


def test_prune_caps_agent_decisions():
    big = {"audit_logs": [], "agent_decisions": [_decision_record(f"a{i}") for i in range(80)]}
    pruned = prune_transient_state(big)
    assert len(pruned["agent_decisions"]) == 50
    assert pruned["agent_decisions"][0]["agent_name"] == "a30"  # kept the *latest*
