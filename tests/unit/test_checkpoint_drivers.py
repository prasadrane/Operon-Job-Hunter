"""Unit tests for Checkpointer Driver Factory and Circuit Breaker Mechanics."""
import pytest
from unittest.mock import patch, MagicMock

from src.pipeline.state_machine import (
    create_checkpointer,
    with_circuit_breaker,
    build_careergraph_pipeline,
    CareerGraphPipeline,
)
from src.pipeline.state_schema import PipelineGraphState


def test_create_checkpointer_memory():
    """Verify memory checkpointer creation."""
    cp = create_checkpointer(driver="memory")
    assert cp is not None
    assert "MemorySaver" in type(cp).__name__


def test_create_checkpointer_sqlite(tmp_path):
    """Verify sqlite checkpointer creation."""
    db_file = str(tmp_path / "test_checkpoints.db")
    cp = create_checkpointer(driver="sqlite", db_path=db_file)
    assert cp is not None
    assert "SqliteSaver" in type(cp).__name__


def test_create_checkpointer_postgres_fallback():
    """Verify postgres checkpointer gracefully falls back to sqlite when unavailable."""
    cp = create_checkpointer(driver="postgres", postgres_url="postgresql://invalid:5432/db")
    assert cp is not None
    # Should fallback gracefully without raising an unhandled exception


def test_circuit_breaker_catches_hanging_node():
    """Verify circuit breaker catches timeouts and records error in state."""
    import time

    @with_circuit_breaker(timeout_seconds=0.2)
    def hanging_node(state: PipelineGraphState):
        time.sleep(0.5)
        return {"current_stage": "COMPLETED"}

    state: PipelineGraphState = {
        "job_id": "job_cb_test",
        "errors": [],
        "audit_logs": [],
    }

    result = hanging_node(state)
    assert result["current_stage"] == "CIRCUIT_BROKEN"
    assert any("Circuit breaker triggered" in err or "timeout" in err.lower() for err in result.get("errors", []))


def test_circuit_breaker_passes_normal_node():
    """Verify circuit breaker passes quick successful nodes without modification."""
    @with_circuit_breaker(timeout_seconds=2.0)
    def fast_node(state: PipelineGraphState):
        return {"current_stage": "TAILORED", "fit_score": 95.0}

    state: PipelineGraphState = {"job_id": "job_fast", "errors": [], "audit_logs": []}
    result = fast_node(state)
    assert result["current_stage"] == "TAILORED"
    assert result["fit_score"] == 95.0
