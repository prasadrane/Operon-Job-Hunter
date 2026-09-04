"""Unit tests for Stage 5 RetrospectiveAgent sync."""

import importlib
from unittest.mock import MagicMock
import pytest

_retro_mod = importlib.import_module("src.pipeline.5_lifecycle.retrospective_agent")
RetrospectiveAgent = getattr(_retro_mod, "RetrospectiveAgent")


def test_retrospective_agent_sync_insights_to_graph(tmp_path):
    """Verify RetrospectiveAgent syncs ATS quirks into core memory directives."""
    mock_memory = MagicMock()
    quirks_file = str(tmp_path / "test_quirks.json")

    agent = RetrospectiveAgent(quirks_path=quirks_file, core_memory=mock_memory)

    mock_quirks = {
        "Stripe": {
            "resume_upload": {
                "healed_selector": "input[type='file']",
                "action": "set_input_files",
            }
        },
        "Netflix": {
            "submit_button": {
                "healed_selector": "button[type='submit']",
                "action": "click",
            }
        },
    }

    synced_count = agent.sync_insights_to_graph(mock_quirks)
    assert synced_count == 2
    assert mock_memory.save_directive.call_count == 2
