# tests/unit/test_brain_flip.py
import json
from pathlib import Path


def test_flip_state_and_retirements(tmp_path):
    reg_data = {
        "models": [
            {"version": "v1-q4", "model_name": "career-brain-q4", "active": True},
            {"version": "tailor-v1", "model_name": "career-brain-tailor-v1", "mode": "tailoring"},
            {"version": "qa-v1", "model_name": "career-brain-qa-v1", "mode": "qa"},
        ],
        "active_modes": {"tailoring": "tailor-v1", "qa": "qa-v1"},
    }
    p = tmp_path / "models.json"
    p.write_text(json.dumps(reg_data), encoding="utf-8")
    from src.brain.model_registry import ModelRegistry
    reg = ModelRegistry(p)
    assert reg.get_model_for_mode("tailoring")["model_name"] == "career-brain-tailor-v1"
    assert reg.get_model_for_mode("qa")["model_name"] == "career-brain-qa-v1"
    assert reg.get_model_for_mode("avatar")["model_name"] == "career-brain-q4"  # fallback until qa avatar entry
    # rollback path
    reg.set_active_for_mode("tailoring", "v1-q4")
    assert ModelRegistry(p).get_model_for_mode("tailoring")["model_name"] == "career-brain-q4"
