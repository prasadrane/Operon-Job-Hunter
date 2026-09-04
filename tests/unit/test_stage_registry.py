# tests/unit/test_stage_registry.py
from unittest.mock import MagicMock, patch

import pytest

from src.core.stages.stage_registry import (
    can_handle, get_capability, list_capabilities, run_stage,
)


def test_capabilities_registered():
    names = [c.name for c in list_capabilities()]
    assert names == ["evaluation", "tailoring", "submission"]
    cap = get_capability("evaluation")
    assert "job_id" in cap.input_requirements
    assert "fit_score" in cap.output_produces
    assert cap.configurable_params == []


def test_unknown_stage_raises_with_options():
    with pytest.raises(KeyError) as exc:
        get_capability("nope")
    assert "evaluation" in str(exc.value)


def test_can_handle_true_false():
    full = {"job_id": "j", "url": "u", "company": "c", "title": "t"}
    assert can_handle("evaluation", full) is True
    assert can_handle("evaluation", {"job_id": "j"}) is False
    # None-valued required key does not count as present data
    assert can_handle("evaluation", {**full, "title": None}) is False


def test_run_stage_delegates_to_node_function():
    fake_node = MagicMock(return_value={"fit_score": 88.0})
    fake_mod = MagicMock(node_discover_and_evaluate=fake_node)
    with patch("importlib.import_module", return_value=fake_mod):
        out = run_stage("evaluation", {"job_id": "j"})
    assert out == {"fit_score": 88.0}
    fake_node.assert_called_once_with({"job_id": "j"})
