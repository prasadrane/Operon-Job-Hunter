"""Tests for typed state engine: SeverityLevel monotonic ordering and hard_blocks/soft_flags reducers.

Contract task-1: state_schema.py additions.
"""
import pytest

from src.pipeline.state_schema import (
    PipelineGraphState,
    SeverityLevel,
    hard_blocks_reducer,
    soft_flags_reducer,
    validation_level_reducer,
)


# ── SeverityLevel monotonic ordering ──────────────────────────────────────────

class TestSeverityLevelOrdering:
    def test_enum_values_ordered(self):
        """SeverityLevel must have CLEAN < WARNING < CRITICAL_RETRY < FATAL_BLOCK."""
        assert SeverityLevel.CLEAN.value < SeverityLevel.WARNING.value
        assert SeverityLevel.WARNING.value < SeverityLevel.CRITICAL_RETRY.value
        assert SeverityLevel.CRITICAL_RETRY.value < SeverityLevel.FATAL_BLOCK.value

    def test_comparison_operators(self):
        """Enum members must support < > comparisons via value."""
        assert SeverityLevel.CLEAN < SeverityLevel.WARNING
        assert SeverityLevel.WARNING < SeverityLevel.CRITICAL_RETRY
        assert SeverityLevel.CRITICAL_RETRY < SeverityLevel.FATAL_BLOCK
        assert SeverityLevel.FATAL_BLOCK > SeverityLevel.CLEAN

    def test_all_four_levels_exist(self):
        levels = {s.name for s in SeverityLevel}
        assert levels == {"CLEAN", "WARNING", "CRITICAL_RETRY", "FATAL_BLOCK"}


# ── hard_blocks reducer: monotonic escalation only ────────────────────────────

class TestHardBlocksReducer:
    def test_adds_new_blocks(self):
        """Reducer should append new hard blocks."""
        current = ["work_auth"]
        new_addition = ["h1b_denied"]
        result = hard_blocks_reducer(current, new_addition)
        assert "work_auth" in result
        assert "h1b_denied" in result

    def test_never_removes_existing_blocks(self):
        """Reducer must never downgrade — existing blocks persist."""
        current = ["work_auth", "h1b_denied"]
        new_addition = []  # empty update
        result = hard_blocks_reducer(current, new_addition)
        assert result == ["work_auth", "h1b_denied"]

    def test_deduplication(self):
        """Duplicate blocks should not be added twice."""
        current = ["work_auth"]
        new_addition = ["work_auth"]
        result = hard_blocks_reducer(current, new_addition)
        assert result.count("work_auth") == 1

    def test_empty_initial_state(self):
        """Reducer works from empty initial state."""
        result = hard_blocks_reducer([], ["new_block"])
        assert result == ["new_block"]

    def test_both_empty(self):
        result = hard_blocks_reducer([], [])
        assert result == []


# ── soft_flags reducer ────────────────────────────────────────────────────────

class TestSoftFlagsReducer:
    def test_accumulates_flags(self):
        result = soft_flags_reducer(["eval_warning"], ["score_margin"])
        assert "eval_warning" in result
        assert "score_margin" in result

    def test_deduplication(self):
        result = soft_flags_reducer(["flag_a"], ["flag_a"])
        assert result.count("flag_a") == 1


# ── validation_level reducer: only escalate ───────────────────────────────────

class TestValidationLevelReducer:
    def test_escalates_to_higher_severity(self):
        result = validation_level_reducer(SeverityLevel.CLEAN, SeverityLevel.WARNING)
        assert result == SeverityLevel.WARNING

    def test_never_downgrades(self):
        result = validation_level_reducer(SeverityLevel.FATAL_BLOCK, SeverityLevel.CLEAN)
        assert result == SeverityLevel.FATAL_BLOCK

    def test_same_level_stays(self):
        result = validation_level_reducer(SeverityLevel.WARNING, SeverityLevel.WARNING)
        assert result == SeverityLevel.WARNING

    def test_handles_none_current(self):
        """First write — current is None/missing — should take new value."""
        result = validation_level_reducer(None, SeverityLevel.WARNING)
        assert result == SeverityLevel.WARNING


# ── PipelineGraphState TypedDict has new fields ──────────────────────────────

class TestPipelineGraphStateFields:
    def test_has_hard_blocks(self):
        """PipelineGraphState must accept hard_blocks field."""
        state: PipelineGraphState = {"hard_blocks": ["test_block"]}  # type: ignore
        assert state["hard_blocks"] == ["test_block"]

    def test_has_soft_flags(self):
        state: PipelineGraphState = {"soft_flags": ["flag1"]}  # type: ignore
        assert state["soft_flags"] == ["flag1"]

    def test_has_validation_level(self):
        state: PipelineGraphState = {"validation_level": SeverityLevel.CLEAN}  # type: ignore
        assert state["validation_level"] == SeverityLevel.CLEAN

    def test_has_provenance_metadata(self):
        state: PipelineGraphState = {"provenance_metadata": {"source": "test"}}  # type: ignore
        assert state["provenance_metadata"]["source"] == "test"
